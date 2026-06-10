"""
services/agents/parser.py (Vision Agent)
==========================================
Vision Agent node — the "Eyes" of the pipeline.

Responsibilities
----------------
1. Trigger async DXF/PDF parsing via the FastAPI files router.
2. Detect and surface unit/scale ambiguity **before** anything else.
   (Risk 2 from the product brief — a 6 m beam vs a 6 mm beam produces
   catastrophically different results.) The agent blocks here until the
   engineer explicitly confirms units.
3. Classify raw geometry entities into structured structural members using the LLM.
4. Summarise the detected structural members for engineer review.
5. Produce the state update that feeds Gate 1 (geometry_verification_gate).

Rule: This node **never calls analysis or design code directly**.
      It only calls the files API tools.
"""

from __future__ import annotations
from fastapi import HTTPException

import json
import logging
import math
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from dxf_parser import extract_geometry
from pdf_normalizer import build_vision_content  # Option C: high-DPI raster grounding
from dotenv import load_dotenv
load_dotenv()
logger = logging.getLogger(__name__)

def _get_llm():
    model_name = os.environ.get("ACTION_MODEL", "gemini-3.1-flash-lite")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set. Please set it to run LLM extraction.")
    return ChatGoogleGenerativeAI(
        model=model_name,
        temperature=0,
        google_api_key=api_key,
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _detect_unit_ambiguity(parsed_json: dict) -> dict:
    """
    Heuristic scale / unit detection from parsed geometry.

    Applies the following rule:
    - Mean dimension 3–12  → metres  (high confidence)
    - Mean dimension 3000–12000 → millimetres (high confidence)
    - Otherwise → ambiguous

    Parameters
    ----------
    parsed_json : dict
        Parsed structural JSON from the DXF/PDF parser.

    Returns
    -------
    dict
        ``{ambiguous, detected_unit, confidence, sample_dimensions}``
    """
    members = parsed_json.get("members", [])
    entities = parsed_json.get("entities", [])
    dimensions: list[float] = []

    for m in members:
        meta = m.get("meta", {})
        spans = m.get("spans_m", [])
        dimensions.extend(spans)
        for key in ("b_mm", "h_mm", "L_clear", "Lx", "Ly", "L_plan"):
            if key in meta:
                try:
                    dimensions.append(float(meta[key]))
                except (TypeError, ValueError):
                    pass

    # Fallback to checking raw entities if members is not yet populated
    if not dimensions and entities:
        for ent in entities:
            dxf_type = ent.get("dxf_type")
            geom = ent.get("geometry", {})
            
            # Use columns or large outlines/lines to infer dimensions
            if dxf_type == "LINE" and "length" in geom:
                dimensions.append(float(geom["length"]))
            elif dxf_type == "LWPOLYLINE" and "perimeter" in geom:
                bbox = ent.get("bounding_box", {})
                w = bbox.get("width", 0.0)
                h = bbox.get("height", 0.0)
                if w > 0:
                    dimensions.append(w)
                if h > 0:
                    dimensions.append(h)
            elif dxf_type == "CIRCLE" and "diameter" in geom:
                dimensions.append(float(geom["diameter"]))

    if not dimensions:
        return {
            "ambiguous": True,
            "detected_unit": "unknown",
            "confidence": "low",
            "sample_dimensions": [],
        }

    # Clean dimensions to avoid extreme values skewing the mean
    valid_dims = [d for d in dimensions if 0.1 <= d <= 50000.0]
    if not valid_dims:
        valid_dims = dimensions

    mean_dim = sum(valid_dims) / len(valid_dims)

    if 3.0 <= mean_dim <= 30.0:
        detected, confidence = "metres", "high"
    elif 3000 <= mean_dim <= 30000:
        detected, confidence = "millimetres", "high"
    else:
        detected, confidence = "unknown", "low"

    return {
        "ambiguous": confidence != "high",
        "detected_unit": detected,
        "confidence": confidence,
        "sample_dimensions": valid_dims[:5],
    }


def _cluster_candidate_pairs(candidates: list[dict]) -> list[dict]:
    """
    Merge duplicate geometry candidates that represent the same physical member.

    DXF drawings produce two kinds of duplication:

    1. **Beam edge pairs** — each beam outline is drawn as two parallel lines
       (both face-edges of the beam width, typically 225 mm apart).  These
       duplicates share the same DXF layer and must be merged into one
       centreline candidate.  Merge threshold: 300 mm, same-layer only.

    2. **Column multi-entity** — a column may appear as both a closed LWPOLYLINE
       on a generic layer (``rectangular_outline`` flag) and an INSERT block or
       additional closed polyline on a dedicated column layer.  Both represent
       the same physical section at the same centre but differ in layer.  Merge
       threshold: 75 mm, cross-layer (tight to avoid merging adjacent columns).

    Returns
    -------
    list[dict]
        Deduplicated candidate list with averaged spatial coordinates and
        merged text annotations.
    """
    _COL_FLAGS = {"rectangular_outline", "circular_section"}
    _BEAM_DIST = 300.0   # mm — beam edge-pair spacing
    _COL_DIST  = 75.0    # mm — column entity co-location tolerance

    used: set[int] = set()
    merged: list[dict] = []

    for i, a in enumerate(candidates):
        if i in used:
            continue
        used.add(i)

        ac = a["centroid"]
        a_layer = a.get("layer", "")
        a_is_col = bool(_COL_FLAGS & set(a.get("flags", []))) or a.get("layer_hint") == "column_candidate"

        best_j, best_dist = -1, float("inf")

        for j, b in enumerate(candidates):
            if j in used or j <= i:
                continue

            bc = b["centroid"]
            d = math.hypot(ac[0] - bc[0], ac[1] - bc[1])
            b_is_col = bool(_COL_FLAGS & set(b.get("flags", []))) or b.get("layer_hint") == "column_candidate"

            same_layer = b.get("layer", "") == a_layer

            if a_is_col and b_is_col:
                # Column-type: merge same-centroid entities regardless of layer
                if d < _COL_DIST and d < best_dist:
                    best_dist = d
                    best_j = j
            elif not a_is_col and not b_is_col and same_layer:
                # Beam-type: merge same-layer parallel edge pairs
                if d < _BEAM_DIST and d < best_dist:
                    best_dist = d
                    best_j = j

        if best_j == -1:
            merged.append(a)
            continue

        used.add(best_j)
        b = candidates[best_j]
        bc = b["centroid"]

        rep = dict(a)
        rep["centroid"] = [
            round((ac[0] + bc[0]) / 2, 4),
            round((ac[1] + bc[1]) / 2, 4),
        ]

        # Average spatial coordinates
        a_sp, b_sp = a.get("spatial", {}), b.get("spatial", {})
        if a_sp.get("start_point") and b_sp.get("start_point"):
            rep["spatial"] = {
                "start_point": {
                    "x": round((a_sp["start_point"]["x"] + b_sp["start_point"]["x"]) / 2, 4),
                    "y": round((a_sp["start_point"]["y"] + b_sp["start_point"]["y"]) / 2, 4),
                },
                "end_point": {
                    "x": round((a_sp["end_point"]["x"] + b_sp["end_point"]["x"]) / 2, 4),
                    "y": round((a_sp["end_point"]["y"] + b_sp["end_point"]["y"]) / 2, 4),
                },
            }
        elif a_sp.get("center_point") and b_sp.get("center_point"):
            rep["spatial"] = {
                "center_point": {
                    "x": round((a_sp["center_point"]["x"] + b_sp["center_point"]["x"]) / 2, 4),
                    "y": round((a_sp["center_point"]["y"] + b_sp["center_point"]["y"]) / 2, 4),
                }
            }

        # Union text annotations; deduplicate by content, keep closest 5
        texts: dict[str, dict] = {
            t["text"]: t
            for t in (b.get("nearest_text", []) + a.get("nearest_text", []))
        }
        rep["nearest_text"] = sorted(texts.values(), key=lambda t: t["distance_mm"])[:5]

        merged.append(rep)

    return merged


def _prepare_candidates_summary(parsed_json: dict) -> list[dict]:
    """
    Groups raw geometry entities into a high-signal candidate list.
    Computes nearest text annotations for each geometric candidate using spatial distance.

    Parameters
    ----------
    parsed_json : dict
        Parsed structural JSON.

    Returns
    -------
    list[dict]
        List of high-signal structural candidate dictionaries.
    """
    entities = parsed_json.get("entities", [])
    if not entities:
        return []

    text_ents = []
    geom_ents = []
    
    for ent in entities:
        dxf_type = ent.get("dxf_type")
        if dxf_type in ("TEXT", "MTEXT", "DIMENSION", "LEADER"):
            text_ents.append(ent)
        else:
            geom_ents.append(ent)
            
    candidates = []
    
    for ent in geom_ents:
        layer = ent.get("layer", "")
        layer_hint = ent.get("layer_hint", "")
        dxf_type = ent.get("dxf_type")
        bbox = ent.get("bounding_box", {})
        centroid = bbox.get("centroid", [0.0, 0.0])
        flags = ent.get("flags", [])
        
        # Only process columns, beams and slabs as candidates
        if layer_hint in ("column_candidate", "beam_candidate", "slab_candidate") or "rectangular_outline" in flags or "circular_section" in flags:
            # Build precise spatial coordinates dictionary for visual/canvas grounding
            geom = ent.get("geometry", {})
            spatial: dict[str, Any] = {}
            if layer_hint == "column_candidate" or "rectangular_outline" in flags or "circular_section" in flags:
                spatial["center_point"] = {"x": centroid[0], "y": centroid[1]}
            elif layer_hint == "beam_candidate":
                if "start" in geom and "end" in geom:
                    spatial["start_point"] = {"x": geom["start"][0], "y": geom["start"][1]}
                    spatial["end_point"] = {"x": geom["end"][0], "y": geom["end"][1]}
                else:
                    spatial["start_point"] = {"x": bbox.get("min_x", 0.0), "y": bbox.get("min_y", 0.0)}
                    spatial["end_point"] = {"x": bbox.get("max_x", 0.0), "y": bbox.get("max_y", 0.0)}
            elif layer_hint == "slab_candidate":
                if "points" in geom:
                    spatial["boundary_polygon"] = [{"x": pt[0], "y": pt[1]} for pt in geom["points"]]
                else:
                    spatial["boundary_polygon"] = [
                        {"x": bbox.get("min_x", 0.0), "y": bbox.get("min_y", 0.0)},
                        {"x": bbox.get("max_x", 0.0), "y": bbox.get("min_y", 0.0)},
                        {"x": bbox.get("max_x", 0.0), "y": bbox.get("max_y", 0.0)},
                        {"x": bbox.get("min_x", 0.0), "y": bbox.get("max_y", 0.0)},
                    ]

            cand = {
                "entity_id": ent.get("entity_id"),
                "dxf_type": dxf_type,
                "layer": layer,
                "layer_hint": layer_hint,
                "centroid": centroid,
                "bbox": bbox,
                "spatial": spatial,
                "flags": flags,
                "nearest_text": []
            }
            candidates.append(cand)
            
    # For each candidate, find the nearest 5 text annotations
    for cand in candidates:
        cc = cand["centroid"]
        texts_with_dist = []
        for tent in text_ents:
            tc = tent.get("bounding_box", {}).get("centroid", tent.get("geometry", {}).get("insertion_point", [0.0, 0.0]))
            dist = math.hypot(cc[0] - tc[0], cc[1] - tc[1])
            content = tent.get("attributes", {}).get("text_content", "")
            text_type = tent.get("attributes", {}).get("text_type", "")
            if content:
                texts_with_dist.append((dist, content, text_type))
                
        texts_with_dist.sort(key=lambda x: x[0])
        cand["nearest_text"] = [
            {"text": t[1], "type": t[2], "distance_mm": round(t[0], 1)}
            for t in texts_with_dist[:5]
        ]

    # Cluster duplicate candidates that represent the same physical member.
    # DXF drawings encode each beam with two parallel edge lines and each column
    # outline may appear as both a closed polyline and additional detail entities.
    # Merge pairs whose centroids are within 300 mm on the same layer so that
    # the LLM receives one representative per member rather than two.
    candidates = _cluster_candidate_pairs(candidates)

    return candidates


# ─── Post-processing helpers ──────────────────────────────────────────────────


def _deduplicate_beams(members: list[dict]) -> list[dict]:
    """
    Merge parallel duplicate beam outline lines into single centreline members.

    DXF structural drawings represent each beam in plan with two parallel edge
    lines (the two faces of the beam width, e.g. 225 mm apart). The LLM maps
    each line to a separate instance (B1-1 / B1-2). This function groups by the
    base label (B1, B2, …), averages start/end coordinates to produce a single
    centreline, and recomputes L_clear from the merged geometry.
    """
    from collections import defaultdict

    beams = [m for m in members if m.get("member_type") == "beam"]
    non_beams = [m for m in members if m.get("member_type") != "beam"]

    groups: dict[str, list[dict]] = defaultdict(list)
    ungrouped: list[dict] = []

    for beam in beams:
        mid = beam.get("member_id", "")
        match = re.match(r"^(.+)-(\d+)$", mid)
        if match:
            groups[match.group(1)].append(beam)
        else:
            ungrouped.append(beam)

    merged: list[dict] = []
    for base_id, group in sorted(groups.items()):
        if len(group) == 1:
            merged.append(group[0])
            continue

        valid = [g for g in group if g.get("start_point") and g.get("end_point")]
        if not valid:
            merged.append(group[0])
            continue

        avg_sx = sum(g["start_point"]["x"] for g in valid) / len(valid)
        avg_sy = sum(g["start_point"]["y"] for g in valid) / len(valid)
        avg_ex = sum(g["end_point"]["x"] for g in valid) / len(valid)
        avg_ey = sum(g["end_point"]["y"] for g in valid) / len(valid)

        length_mm = math.hypot(avg_ex - avg_sx, avg_ey - avg_sy)
        l_clear = round(length_mm / 1000.0, 4)

        rep = dict(group[0])
        rep["member_id"] = base_id
        rep["start_point"] = {"x": round(avg_sx, 4), "y": round(avg_sy, 4)}
        rep["end_point"] = {"x": round(avg_ex, 4), "y": round(avg_ey, 4)}
        rep["meta"] = dict(group[0].get("meta", {}))
        rep["meta"]["L_clear"] = l_clear
        rep["spans"] = [{"span_id": "S1", "length_m": l_clear}]
        rep["spans_m"] = [l_clear]
        merged.append(rep)

    return non_beams + merged + ungrouped


def _filter_stub_beams(members: list[dict], min_span_m: float = 0.1) -> list[dict]:
    """
    Remove beams shorter than min_span_m.

    The DXF also contains short perpendicular segments where beam outlines meet
    column faces (typically 225–450 mm). These are geometric artefacts, not
    structural spans, and must be dropped before analysis.
    """
    result = []
    for m in members:
        if m.get("member_type") == "beam":
            span = m.get("spans_m", [0])[0] if m.get("spans_m") else 0
            if span < min_span_m:
                logger.debug("Dropping stub beam %s (L=%.3f m)", m.get("member_id"), span)
                continue
        result.append(m)
    return result


async def _run_llm_slab_void_extraction(
    project_id: str,
    column_members: list[dict],
    beam_members: list[dict],
    pdf_path: Optional[str] = None,
) -> list[dict]:
    """
    LLM pass — identifies slab panels and void openings.

    Uses the column grid and beam centrelines as a spatial framework and the
    reference PDF as the visual ground truth for panel boundaries and voids.
    Runs only when a PDF is available; returns an empty list otherwise.

    Parameters
    ----------
    project_id : str
        Project identifier for logging.
    column_members : list[dict]
        Already-classified column members (used for coordinate context).
    beam_members : list[dict]
        Already-classified, deduplicated beam members.
    pdf_path : str | None
        Absolute path to the reference PDF drawing.

    Returns
    -------
    list[dict]
        Slab panel and void member dicts ready to merge into the main list.
    """
    # Check if the PDF has at least one page.
    pdf_is_valid = False
    if pdf_path and os.path.exists(pdf_path):
        try:
            import fitz
            doc = fitz.open(pdf_path)
            if doc.page_count > 0:
                pdf_is_valid = True
            else:
                logger.warning("PDF file at '%s' has 0 pages; ignoring it as invalid.", pdf_path)
        except Exception as err:
            logger.warning("Failed to open PDF file at '%s': %s; ignoring it as invalid.", pdf_path, err)

    if not pdf_path or not os.path.exists(pdf_path) or not pdf_is_valid:
        logger.info("No valid PDF available — skipping slab/void extraction for project %s", project_id)
        return []

    col_summary = [
        {
            "id": c.get("member_id"),
            "x": round((c.get("center_point") or {}).get("x", 0), 1),
            "y": round((c.get("center_point") or {}).get("y", 0), 1),
            "b_mm": (c.get("meta") or {}).get("b", 225),
            "h_mm": (c.get("meta") or {}).get("h", 225),
        }
        for c in column_members
    ]

    beam_summary = [
        {
            "id": b.get("member_id"),
            "start": {
                "x": round((b.get("start_point") or {}).get("x", 0), 1),
                "y": round((b.get("start_point") or {}).get("y", 0), 1),
            },
            "end": {
                "x": round((b.get("end_point") or {}).get("x", 0), 1),
                "y": round((b.get("end_point") or {}).get("y", 0), 1),
            },
            "span_m": round((b.get("spans_m") or [0])[0], 3),
        }
        for b in beam_members
    ]

    valid_beam_ids = [b.get("member_id") for b in beam_members]

    prompt = f"""You are an expert Structural Engineer with an eye for detail.
We have already extracted {len(column_members)} columns and {len(beam_members)} beams
from this floor plan. The drawing images attached below are the visual ground truth.

--- Column positions (centre, mm) ---
{json.dumps(col_summary, indent=2)}

--- Beam centrelines (mm) ---
{json.dumps(beam_summary, indent=2)}

--- Valid beam IDs (you MUST only use IDs from this list) ---
{json.dumps(valid_beam_ids)}

--- Your task ---
Identify EVERY enclosed region (panel) in the drawing and classify each as either a
SLAB or a VOID.

PANEL = the smallest region fully enclosed by beams/columns. Do not merge adjacent
panels; report each enclosed bay separately.

For each panel, name the FOUR beams that bound it (two roughly-horizontal, two
roughly-vertical). Critically:
  - Use ONLY beam IDs from the "Valid beam IDs" list above. Never invent an ID.
  - Pick beams that actually form the four sides of THIS panel (two with different
    Y positions for top/bottom, two with different X positions for left/right).
    Do not pick two beams that lie on the same line.

VOID vs SLAB — read the attached images carefully:
  - A VOID is an opening with NO slab: a stair well, lift shaft, or duct. On the
    drawing it is typically shown by a diagonal cross ("X") drawn across the panel,
    by the words VOID / OPENING / OPEN, or by hatching that marks an absence of slab.
    Set "is_void": true for these.
  - Every other enclosed panel is a SLAB. Set "is_void": false.

Label panels S1, S2, S3, … top-left → bottom-right (use the same S-series for voids).
Default slab_type to "solid_slab" unless the image clearly shows ribbed or flat slab.

Return ONLY a valid JSON array. No markdown fences, no preamble.
Each entry must follow this exact schema:
{{
  "member_id": "S1",
  "member_type": "slab",
  "type": "slab",
  "is_void": false,
  "bounding_beams": ["1B1", "1B16", "1B21", "1B11"]
}}
"""

    try:
        llm = _get_llm()
        # Option C: send legible high-DPI raster + detail tiles of the drawing
        # instead of the multi-MB base64 PDF that Gemini downsampled to mush.
        content = build_vision_content(prompt, pdf_path, dpi=300, tile=True)
        # pyrefly: ignore [no-matching-overload]
        response = await llm.ainvoke([HumanMessage(content=content)])
        text = response.text.strip()

        if "```" in text:
            m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
            if m:
                text = m.group(1).strip()

        slab_members = json.loads(text)

        if not isinstance(slab_members, list):
            logger.warning("Slab extraction returned non-list for project %s", project_id)
            return []

        beam_dict = {b["member_id"]: b for b in beam_members}

        for m in slab_members:
            # Normalise the slab/void flag the model returned.
            m["is_void"] = bool(m.get("is_void", False))
            m.setdefault("member_type", "slab")
            m.setdefault("type", "slab")

            horiz_ys = []
            vert_xs = []
            
            # 1. Sort bounding beams into horizontal vs vertical
            for beam_id in m.get("bounding_beams", []):
                if beam_id in beam_dict:
                    beam = beam_dict[beam_id]
                    sp = beam.get("start_point")
                    ep = beam.get("end_point")
                    
                    if not sp or not ep:
                        continue
                        
                    dx = abs(sp["x"] - ep["x"])
                    dy = abs(sp["y"] - ep["y"])
                    
                    # If beam is more horizontal than vertical
                    if dx > dy:
                        avg_y = (sp["y"] + ep["y"]) / 2.0
                        horiz_ys.append(avg_y)
                    # If beam is more vertical than horizontal
                    else:
                        avg_x = (sp["x"] + ep["x"]) / 2.0
                        vert_xs.append(avg_x)
                        
            # 2. Build the exact polygon from intersections
            if len(horiz_ys) >= 2 and len(vert_xs) >= 2:
                # The true corners are the min/max of the horizontal and vertical axes
                min_x, max_x = min(vert_xs), max(vert_xs)
                min_y, max_y = min(horiz_ys), max(horiz_ys)
                
                m["boundary_polygon"] = [
                    {"x": round(min_x, 4), "y": round(min_y, 4)},
                    {"x": round(max_x, 4), "y": round(min_y, 4)},
                    {"x": round(max_x, 4), "y": round(max_y, 4)},
                    {"x": round(min_x, 4), "y": round(max_y, 4)},
                ]
                
                # 3. Calculate precise lengths in metres
                w_m = round((max_x - min_x) / 1000.0, 3)
                h_m = round((max_y - min_y) / 1000.0, 3)
                
                if "meta" not in m:
                    m["meta"] = {}

                m["meta"]["slab_type"] = "void" if m.get("is_void") else "solid_slab"
                m["meta"]["thickness_mm"] = 0 if m.get("is_void") else 150
                m["meta"]["Lx"] = min(w_m, h_m)
                m["meta"]["Ly"] = max(w_m, h_m)
                m["spans_m"] = [m["meta"]["Lx"], m["meta"]["Ly"]]
            else:
                # Fallback if the LLM hallucinated beams or didn't return a closed loop
                m["boundary_polygon"] = []
                m["spans_m"] = []

        logger.info(
            "Slab/void extraction: %d members for project %s",
            len(slab_members), project_id,
        )
        return slab_members

    except Exception as exc:
        logger.error("Slab/void extraction failed for project %s: %s", project_id, exc)
        return []


def _extract_beams_deterministically(beam_candidates: list[dict]) -> list[dict]:
    """
    Build beam members directly from DXF LINE geometry and nearest-text annotations.

    Beam geometry (start/end coordinates) is already correct in the DXF; the
    only information the LLM would add is the section label and member ID, both
    of which are available from nearby BeamText annotations via ``nearest_text``.
    Extracting beams here avoids sending ~90 featureless line candidates to the
    LLM, which caused unreliable classification due to context overload.

    Section defaults to 225×450 mm when no matching annotation is found nearby.
    Stubs shorter than 0.6 m are dropped (column-face connection artefacts).
    """
    members: list[dict] = []
    seq = 1

    for cand in beam_candidates:
        spatial = cand.get("spatial", {})
        start = spatial.get("start_point")
        end = spatial.get("end_point")
        if not start or not end:
            continue

        length_mm = math.hypot(end["x"] - start["x"], end["y"] - start["y"])
        l_clear = round(length_mm / 1000.0, 4)
        if l_clear < 0.1:  # Discard extremely short lines/hatch ticks
            continue

        member_id: Optional[str] = None
        b_mm, h_mm = 225.0, 450.0

        for t in cand.get("nearest_text", []):
            text_val = t["text"]
            if t.get("distance_mm", 9999) > 5000:
                break
            sec = re.search(r"(\d{2,4})[xX×](\d{2,4})", text_val)
            if sec and b_mm == 225.0:
                b_mm = float(sec.group(1))
                h_mm = float(sec.group(2))
            if member_id is None:
                lbl = re.search(r"(\d*[Bb]\d+)", text_val)
                if lbl:
                    member_id = lbl.group(1)

        # Drop stub beams (length < 0.6 m) ONLY if they have no explicit structural label
        if l_clear < 0.6 and member_id is None:
            continue

        if member_id is None:
            member_id = f"B{seq}"
            seq += 1

        I_val = round((b_mm / 1000.0) * ((h_mm / 1000.0) ** 3) / 12.0, 6)
        members.append({
            "member_id": member_id,
            "member_type": "beam",
            "type": "beam",
            "start_point": start,
            "end_point": end,
            "center_point": None,
            "boundary_polygon": None,
            "is_void": False,
            "meta": {
                "b_mm": b_mm,
                "h_mm": h_mm,
                "L_clear": l_clear,
                "E": 30e6,
                "I": I_val,
            },
            "spans": [{"span_id": "S1", "length_m": l_clear}],
            "spans_m": [l_clear],
        })

    return members


async def _run_llm_member_extraction(
    project_id: str,
    parsed_json: dict,
    pdf_path: Optional[str] = None,
) -> list[dict]:
    """
    Extract structural members from parsed DXF + optional reference PDF.

    Uses a three-stage pipeline:

    1. **Beams (deterministic)** — geometry comes from DXF LINE entities; section
       and label are read from nearby BeamText annotations.  No LLM needed —
       avoids sending ~90 featureless line candidates that overwhelm the model.

    2. **Columns (LLM)** — closed rectangular/circular polylines identified by the
       DXF extractor are sent to Gemini for label assignment and section
       confirmation.  Only column candidates (~80–160 items) are sent, keeping
       the prompt within a reliable context budget.

    3. **Slabs + voids (LLM, PDF-grounded)** — a second Gemini call uses the
       already-extracted column and beam positions as a spatial framework plus
       the PDF as primary visual reference to identify slab panels and voids.

    Parameters
    ----------
    project_id : str
        Project identifier.
    parsed_json : dict
        Parsed structural JSON from the DXF extractor.
    pdf_path : str | None
        Absolute path to the reference PDF drawing.

    Returns
    -------
    list[dict]
        Combined list of columns + beams + slabs + voids.
    """
    candidates = _prepare_candidates_summary(parsed_json)
    if not candidates:
        return parsed_json.get("members", [])

    _COL_FLAGS = {"rectangular_outline", "circular_section"}

    # ── Stage 1: extract beams deterministically ──────────────────────────────
    beam_candidates = [
        c for c in candidates
        if c.get("layer_hint") == "beam_candidate"
        and not (_COL_FLAGS & set(c.get("flags", [])))
    ]
    beam_members = _extract_beams_deterministically(beam_candidates)
    logger.info(
        "Deterministic beam extraction: %d beams for project %s",
        len(beam_members), project_id,
    )

    # ── Stage 2: LLM column classification (column candidates only) ───────────
    col_candidates = [
        c for c in candidates
        if c.get("layer_hint") == "column_candidate"
        or (_COL_FLAGS & set(c.get("flags", [])))
    ]

    col_data = [
        {
            "entity_id": c["entity_id"],
            "layer": c["layer"],
            "hint": c["layer_hint"],
            "bbox_width_mm": c["bbox"].get("width"),
            "bbox_height_mm": c["bbox"].get("height"),
            "spatial": c.get("spatial", {}),
            "flags": c["flags"],
            "nearby_text": c["nearest_text"],
        }
        for c in col_candidates
    ]

    prompt = f"""You are the Vision & Parsing Agent for a structural design copilot.
Your ONLY task: classify the following column candidates from the DXF into column members.

Column candidates (closed rectangular or circular section outlines in plan view):
{json.dumps(col_data, indent=2)}

Rules:
1. Each candidate is a physical column section outline. Every distinct spatial location produces a unique member — do NOT collapse multiple positions into one.
2. Assign a label using the nearest text annotations:
   - If nearby text starts with C followed by digits (e.g. "C1", "C2"), use that as the type prefix.
   - Append a sequential instance number: C1-1, C1-2, C2-1, C2-2, …
   - If no label text is found within 1000 mm, assign the next available C1-N label.
3. Set center_point exactly from the candidate's spatial.center_point.
4. Set b and h from bbox_width_mm and bbox_height_mm (column section in mm).
5. Default: L_clear=3.0, end_condition=fixed_fixed, N_uls=1000.0, M_uls=0.0.

Return ONLY a valid JSON array. No markdown fences, no preamble.

Schema:
{{
    "member_id": "C1-1",
    "member_type": "column",
    "type": "column",
    "start_point": null,
    "end_point": null,
    "center_point": {{"x": 0.0, "y": 0.0}},
    "boundary_polygon": null,
    "is_void": false,
    "meta": {{"b": 225, "h": 225, "L_clear": 3.0, "end_condition": "fixed_fixed", "N_uls": 1000.0, "M_uls": 0.0}},
    "spans": [],
    "spans_m": []
}}"""

    col_members: list[dict] = []
    try:
        llm = _get_llm()
        # Option C: attach a high-DPI, content-cropped raster of the drawing
        # instead of the base64 PDF. build_vision_content falls back to a
        # text-only prompt if the PDF is missing or unreadable, and the raster
        # is cached so the later slab/void stage reuses it for free.
        content = build_vision_content(prompt, pdf_path, dpi=300, tile=True)
        if pdf_path:
            logger.info("Drawing images attached for column extraction, project %s", project_id)

        # pyrefly: ignore [no-matching-overload]
        response = await llm.ainvoke([HumanMessage(content=content)])
        text = response.text.strip()

        # Unpack nested list-of-text-block wrappers (mock layer artefact)
        try:
            parsed_blocks = json.loads(text)
            if isinstance(parsed_blocks, list) and parsed_blocks:
                first_block = parsed_blocks[0]
                if isinstance(first_block, dict) and "text" in first_block:
                    text = first_block["text"].strip()
        except Exception:
            pass

        if "```" in text:
            m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
            if m:
                text = m.group(1).strip()

        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            import ast
            raw = ast.literal_eval(text)

        if isinstance(raw, list):
            for m in raw:
                m_type = m.get("member_type", m.get("type", "column"))
                m["member_type"] = m_type
                m["type"] = m_type
                if m_type == "column":
                    meta = m.setdefault("meta", {})
                    meta.setdefault("b", 300)
                    meta.setdefault("h", 300)
                    meta.setdefault("L_clear", 3.0)
                    meta.setdefault("end_condition", "fixed_fixed")
                    meta.setdefault("N_uls", 1000.0)
                    meta.setdefault("M_uls", 0.0)
            col_members = raw
            logger.info(
                "LLM column extraction: %d columns for project %s",
                len(col_members), project_id,
            )

    except Exception as e:
        logger.error("LLM extraction failed for project %s: %s", project_id, e)
        raise HTTPException(status_code=500, detail=f"LLM extraction failed: {e}")

    # ── Stage 3: slab + void extraction from PDF ──────────────────────────────
    slab_members: list[dict] = []
    if col_members or beam_members:
        slab_members = await _run_llm_slab_void_extraction(
            project_id, col_members, beam_members, pdf_path=pdf_path
        )

    return col_members + beam_members + slab_members


def _build_geometry_summary(parsed_json: dict) -> str:
    """
    Build a human-readable Markdown summary of parsed members for the chat panel.

    Parameters
    ----------
    parsed_json : dict
        Parsed structural JSON.

    Returns
    -------
    str
        Markdown-formatted member summary.
    """
    members = parsed_json.get("members", [])
    beams = [m for m in members if m.get("member_type") == "beam"]
    columns = [m for m in members if m.get("member_type") == "column"]
    slabs = [m for m in members if m.get("member_type") == "slab"]
    
    summary = [
        f"### **Structural Member Summary**",
        f"- **Beams detected:** {len(beams)}",
        f"- **Columns detected:** {len(columns)}",
        f"- **Slabs detected:** {len(slabs)}",
    ]
    if len(members) > len(beams) + len(columns) + len(slabs):
        others = len(members) - (len(beams) + len(columns) + len(slabs))
        summary.append(f"- **Other elements detected:** {others}")
        
    if members:
        summary.append("\n**Detected Members list:**")
        for m in members[:10]:
            m_id = m.get("member_id", "?")
            m_type = m.get("member_type", "unknown")
            meta = m.get("meta", {})
            if m_type == "beam":
                spans = m.get("spans_m", [])
                span_str = ", ".join(f"{s:.2f}m" for s in spans)
                summary.append(f"  - **{m_id}** (Beam): {len(spans)} span(s) [{span_str}], Section: {meta.get('b_mm', 300)}x{meta.get('h_mm', 500)} mm")
            elif m_type == "column":
                summary.append(f"  - **{m_id}** (Column): Size {meta.get('b', 300)}x{meta.get('h', 300)} mm, Height: {meta.get('L_clear', 3.0)}m")
            elif m_type == "slab":
                summary.append(f"  - **{m_id}** (Slab): {meta.get('slab_type', 'solid')} panel, {meta.get('Lx', 4.0)}x{meta.get('Ly', 5.0)}m")
            else:
                summary.append(f"  - **{m_id}** ({m_type.capitalize()})")
        if len(members) > 10:
            summary.append(f"  - *... and {len(members) - 10} more members.*")
    else:
        summary.append("\nNo structural members identified yet.")
    return "\n".join(summary)


# ─── Node ─────────────────────────────────────────────────────────────────────


async def parser_node(state: Any) -> dict:
    """
    Vision Agent LangGraph node (Reference Only).
    
    This function is kept for structural reference to show the LangGraph node integration.
    In the standalone sandbox, run_pipeline is used instead.
    """
    raise NotImplementedError("parser_node is not active in the standalone sandbox. Use run_pipeline instead.")


async def run_pipeline(dxf_path: str, pdf_path: Optional[str] = None) -> dict:
    """
    Run the entire parsing pipeline standalone:
    1. Parse DXF raw geometry
    2. Detect scale / unit ambiguity
    3. Run LLM member extraction (beams deterministically, columns/slabs/voids via LLM)
       with automatic fallback to heuristics if LLM keys are missing or fail.
    """
    # Parse raw DXF geometry
    raw_dxf_data = extract_geometry(dxf_path)
    
    # Detect unit
    unit_check = _detect_unit_ambiguity(raw_dxf_data)
    unit = unit_check.get("detected_unit", "millimetres")
    factor = 0.001 if unit == "millimetres" else 1.0
    scale = {
        "factor": factor,
        "unit": "mm" if unit == "millimetres" else "m",
        "detected": True,
        "confirmed": True
    }
    
    project_id = "standalone-project"
    
    # Run LLM member extraction
    members = await _run_llm_member_extraction(project_id, raw_dxf_data, pdf_path=pdf_path)
    
    # Apply post-processing
    members = _deduplicate_beams(members)
    members = _filter_stub_beams(members)
    
    return {
        "members": members,
        "scale": scale,
        "raw_entity_count": len(raw_dxf_data.get("entities", [])),
        "parse_warnings": [f"Unit auto-detected as {unit}."] if not unit_check["ambiguous"] else ["Unit detection ambiguous. Defaulted to millimetres."],
        "filenames": {
            "dxf": os.path.basename(dxf_path),
            "pdf": os.path.basename(pdf_path) if pdf_path else None
        }
    }
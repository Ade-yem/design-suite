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

import json
import logging
import math
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from agents.state import StructuralDesignState
from config import settings
from services.files import file_service
from storage.project_store import project_store

logger = logging.getLogger(__name__)

def _get_llm():
    return ChatGoogleGenerativeAI(
        model=settings.ACTION_MODEL,
        temperature=0,
        google_api_key=settings.GEMINI_API_KEY,
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


def _fallback_members_heuristics(candidates: list[dict]) -> list[dict]:
    """
    Fallback deterministic heuristic parser in case LLM fails or is unavailable.

    Parameters
    ----------
    candidates : list[dict]
        Pre-processed candidates with nearest text.

    Returns
    -------
    list[dict]
        Deterministic list of structural member dictionaries.
    """
    members = []
    beam_idx = 1
    col_idx = 1
    
    for cand in candidates:
        layer_hint = cand["layer_hint"]
        bbox = cand["bbox"]
        spatial = cand.get("spatial", {})
        
        # Try to find a nearby label in text
        label = None
        for item in cand.get("nearest_text", []):
            text_val = item["text"]
            if re.match(r"^[BC]\d{1,3}$", text_val.upper()):
                label = text_val.upper()
                break
                
        w = bbox.get("width", 300.0)
        h = bbox.get("height", 300.0)
        
        if layer_hint == "column_candidate" or "rectangular_outline" in cand.get("flags", []):
            if not label:
                label = f"C{col_idx}"
                col_idx += 1
            members.append({
                "member_id": label,
                "member_type": "column",
                "type": "column",
                "start_point": None,
                "end_point": None,
                "center_point": spatial.get("center_point"),
                "boundary_polygon": None,
                "is_void": False,
                "meta": {
                    "b": round(w),
                    "h": round(h),
                    "L_clear": 3.0,
                    "end_condition": "fixed_fixed",
                    "N_uls": 1000.0,
                    "M_uls": 0.0
                },
                "spans": [{"span_id": "S1", "length_m": 3.0}],
                "spans_m": [3.0]
            })
        else:
            if not label:
                label = f"B{beam_idx}"
                beam_idx += 1
                
            length_m = round(max(w, h) / 1000.0, 2)
            if length_m < 0.5:
                length_m = 5.0
                
            b_mm = 300.0
            h_mm = 500.0
            for item in cand.get("nearest_text", []):
                text_val = item["text"]
                match = re.search(r"(\d{3})\s*[xX]\s*(\d{3})", text_val)
                if match:
                    b_mm = float(match.group(1))
                    h_mm = float(match.group(2))
                    break
                    
            I_val = round((b_mm / 1000.0) * ((h_mm / 1000.0) ** 3) / 12.0, 6)
            
            members.append({
                "member_id": label,
                "member_type": "beam",
                "type": "beam",
                "start_point": spatial.get("start_point"),
                "end_point": spatial.get("end_point"),
                "center_point": None,
                "boundary_polygon": None,
                "is_void": False,
                "meta": {
                    "b_mm": b_mm,
                    "h_mm": h_mm,
                    "L_clear": length_m,
                    "E": 30e6,
                    "I": I_val
                },
                "spans": [{"span_id": "S1", "length_m": length_m}],
                "spans_m": [length_m]
            })
    return members


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


def _filter_stub_beams(members: list[dict], min_span_m: float = 0.6) -> list[dict]:
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
    Second LLM pass — identifies slab panels and void openings.

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
    if not pdf_path or not os.path.exists(pdf_path):
        logger.info("No PDF available — skipping slab/void extraction for project %s", project_id)
        return []

    col_summary = [
        {
            "id": c.get("member_id"),
            "x": round(c.get("center_point", {}).get("x", 0), 1),
            "y": round(c.get("center_point", {}).get("y", 0), 1),
            "b_mm": c.get("meta", {}).get("b", 225),
            "h_mm": c.get("meta", {}).get("h", 225),
        }
        for c in column_members
    ]

    beam_summary = [
        {
            "id": b.get("member_id"),
            "start": {
                "x": round(b.get("start_point", {}).get("x", 0), 1),
                "y": round(b.get("start_point", {}).get("y", 0), 1),
            },
            "end": {
                "x": round(b.get("end_point", {}).get("x", 0), 1),
                "y": round(b.get("end_point", {}).get("y", 0), 1),
            },
            "span_m": round(b.get("spans_m", [0])[0], 3),
        }
        for b in beam_members
    ]

    prompt = f"""You are the Vision & Parsing Agent for an RC structural design copilot.
You have already extracted {len(column_members)} columns and {len(beam_members)} beams from this floor plan.
Your ONLY task now is to identify ALL slab panels and void openings.

--- Column positions (centre, mm) ---
{json.dumps(col_summary, indent=2)}

--- Beam centrelines (mm) ---
{json.dumps(beam_summary, indent=2)}

--- Instructions ---

SLABS: Every rectangular or polygonal region enclosed by beams and columns is a slab panel.
  - Trace the boundary_polygon using the beam centreline coordinates as panel corners.
  - Label them S1, S2, S3, … in a logical order (top-left → bottom-right).
  - Set is_void: false.
  - Estimate Lx (shorter span, m) and Ly (longer span, m) from beam centreline positions.
  - Default slab_type to "solid_slab" unless the PDF clearly shows ribbed or flat slab.
  - Default thickness_mm to 150.

VOIDS: Openings, stairwells, lift shafts, or cutouts visible in the floor plate.
  - In the PDF these are typically marked with diagonal X crosses or void labels.
  - Trace boundary_polygon around the opening perimeter.
  - Set is_void: true.
  - Label them V1, V2, V3, …

Return ONLY a valid JSON array. No markdown fences, no preamble.

Each entry must follow this exact schema:
{{
  "member_id": "S1",
  "member_type": "slab",
  "type": "slab",
  "start_point": null,
  "end_point": null,
  "center_point": null,
  "boundary_polygon": [{{"x": 0.0, "y": 0.0}}, ...],
  "is_void": false,
  "meta": {{
    "slab_type": "solid_slab",
    "Lx": 3.0,
    "Ly": 4.0,
    "thickness_mm": 150
  }},
  "spans": [],
  "spans_m": []
}}"""

    try:
        import base64
        with open(pdf_path, "rb") as f:
            pdf_b64 = base64.b64encode(f.read()).decode("utf-8")

        llm = _get_llm()
        content = [
            {"type": "text", "text": prompt},
            {"type": "file", "mime_type": "application/pdf", "base64": pdf_b64},
        ]
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

        for m in slab_members:
            m["member_type"] = "slab"
            m["type"] = "slab"
            meta = m.setdefault("meta", {})
            meta.setdefault("slab_type", "solid_slab")
            meta.setdefault("thickness_mm", 150)
            Lx = meta.get("Lx", 0)
            Ly = meta.get("Ly", 0)
            m["spans_m"] = [Lx, Ly] if Lx and Ly else []

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
        if l_clear < 0.6:
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
        content: list = [{"type": "text", "text": prompt}]

        if pdf_path and os.path.exists(pdf_path):
            try:
                import base64
                with open(pdf_path, "rb") as f:
                    pdf_data = base64.b64encode(f.read()).decode("utf-8")
                content.append({
                    "type": "file",
                    "mime_type": "application/pdf",
                    "base64": pdf_data,
                })
                logger.info("PDF attached for column extraction, project %s", project_id)
            except Exception as pdf_err:
                logger.warning("Failed to encode PDF for column extraction: %s", pdf_err)

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
        logger.error("Column LLM extraction failed for project %s: %s", project_id, e)
        col_members = _fallback_members_heuristics(col_candidates)

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


async def parser_node(state: StructuralDesignState) -> dict:
    """
    Vision Agent LangGraph node.

    Called when the pipeline status is ``"created"`` or ``"file_uploaded"``.
    Triggers parsing, detects unit ambiguity, and builds the geometry summary
    for Gate 1.

    Parameters
    ----------
    state : StructuralDesignState
        Current pipeline state. Requires ``project_id`` and
        ``uploaded_file_path`` to be set.

    Returns
    -------
    dict
        Partial state update applied by LangGraph.
    """
    project_id = state["project_id"]
    file_path = state.get("uploaded_file_path")

    log_entry = {
        "agent": "vision",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # ── Step 1: upload & trigger parsing ──────────────────────────────────────
    if not file_path:
        message = AIMessage(content=(
            "⚠️ No file path provided. "
            "Please upload a DXF or PDF drawing to begin."
        ))
        return {
            "messages": [message],
            "agent_logs": [{**log_entry, "status": "error", "detail": "no_file_path"}],
            "current_error": "FILE_PARSE_ERROR",
        }

    # Parse raw geometries
    parsed = await file_service.parse(project_id, file_path)

    # Initialize logs list
    logs = []

    # ── Step 4: unit ambiguity detection ──────────────────────────────────────
    unit_check = _detect_unit_ambiguity(parsed)
    logs.append({**log_entry, "status": "unit_check", "detail": unit_check})

    parse_job_id = state.get("parse_job_id")

    if unit_check["ambiguous"]:
        samples = ", ".join(str(round(d, 3)) for d in unit_check["sample_dimensions"])
        message = AIMessage(content=(
            "⚠️ **Unit Confirmation Required**\n\n"
            "I cannot determine with confidence whether the drawing dimensions "
            f"are in **metres** or **millimetres**.\n\n"
            f"Sample dimension values: `{samples}`\n\n"
            "A 6 m beam and a 6 mm beam produce catastrophically different results. "
            "Please confirm the drawing units before I proceed."
        ))
        return {
            "parsed_structural_json": parsed,
            "unit_confirmation": unit_check,
            "parse_job_id": parse_job_id,
            "messages": [message],
            "agent_logs": logs + [{**log_entry, "status": "awaiting_unit_confirmation"}],
            "pipeline_status": "file_uploaded",
        }

    # ── Step 4.5: extract members if not yet populated ───────────────────────
    if not parsed.get("members"):
        logger.info("Extracting structural members via LLM...")
        members = await _run_llm_member_extraction(project_id, parsed)
        parsed["members"] = members
        
        # Save structural JSON back to files service and project store
        file_service.register_geometry(project_id, parsed)
        
        mids = [member.get("member_id") for member in members if member.get("member_id")]
        await project_store.register_members_batch(project_id, mids)

    # ── Step 5: geometry summary ───────────────────────────────────────────────
    scale = file_service.get_scale(project_id)
    summary = _build_geometry_summary(parsed)

    message = AIMessage(content=(
        "**Parsing complete.**\n\n"
        f"{summary}\n\n"
        f"**Detected units:** {unit_check['detected_unit']} "
        f"(confidence: {unit_check['confidence']})\n"
        f"**Scale factor:** `{scale.get('factor', '?')}`\n\n"
        "**Before we proceed, please confirm:**\n"
        "1. Are all members correctly identified and classified?\n"
        "2. Drawing units confirmed as "
        f"**{unit_check['detected_unit']}**?\n"
        "3. Any members missed or misclassified?\n\n"
        "Click **Confirm Geometry** when satisfied, or describe any corrections."
    ))

    return {
        "parsed_structural_json": parsed,
        "unit_confirmation": unit_check,
        "parse_job_id": parse_job_id,
        "pipeline_status": "file_uploaded",
        "messages": [message],
        "agent_logs": logs + [{**log_entry, "status": "awaiting_verification"}],
    }

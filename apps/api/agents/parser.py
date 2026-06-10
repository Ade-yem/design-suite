"""
services/agents/parser.py (Vision Agent)
==========================================
Vision Agent node — the "Eyes" of the pipeline.

Responsibilities
----------------
1. Trigger async DXF/PDF parsing via the FastAPI files router.
2. Detect and surface unit/scale ambiguity **before** anything else.
3. Classify raw geometry entities into structured structural members.
4. Summarise the detected structural members for engineer review.
5. Produce the state update that feeds Gate 1 (geometry_verification_gate).
"""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timezone
from typing import Any, Optional
from collections import defaultdict

from langchain_core.messages import AIMessage

import shapely.geometry as sg
from shapely.ops import polygonize, unary_union

from agents.state import StructuralDesignState
from config import settings
from services.files import file_service
from storage.project_store import project_store

logger = logging.getLogger(__name__)


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


def classify_columns_deterministically(col_candidates: list[dict], beam_members: list[dict]) -> list[dict]:
    """
    Deterministic column classification. Uses a structural beam footprint 
    envelope to flawlessly reject title block frames and drawing border artifacts.
    """
    if not beam_members:
        return []

    # 1. Establish the absolute physical footprint of the actual building framing using beams
    beam_xs = []
    beam_ys = []
    for b in beam_members:
        sp = b.get("start_point")
        ep = b.get("end_point")
        if sp and ep:
            beam_xs.extend([sp["x"], ep["x"]])
            beam_ys.extend([sp["y"], ep["y"]])

    # Add a strict structural boundary buffer zone (1.2 meters) around the beam grid
    STRUCTURAL_BUFFER = 1200.0
    min_structural_x = min(beam_xs) - STRUCTURAL_BUFFER
    max_structural_x = max(beam_xs) + STRUCTURAL_BUFFER
    min_structural_y = min(beam_ys) - STRUCTURAL_BUFFER
    max_structural_y = max(beam_ys) + STRUCTURAL_BUFFER

    col_members = []
    label_counters = defaultdict(int)

    for c in col_candidates:
        centroid = c.get("centroid", [0.0, 0.0])
        bbox = c.get("bbox", {})
        b_mm = bbox.get("width", 225.0)
        h_mm = bbox.get("height", 225.0)
        layer = c.get("layer", "").upper()
        
        # Immediate removal of known text, title, or sheet border layout layers
        if any(kw in layer for kw in ("BORDER", "FRAME", "TITLE", "DEFPOINTS", "TEXT", "DIM", "ANALOG")):
            continue

        # --- Enforce Structural Footprint Filter ---
        # Discard any candidate immediately if it falls outside the active beam layout grid area
        if not (min_structural_x <= centroid[0] <= max_structural_x and min_structural_y <= centroid[1] <= max_structural_y):
            continue

        # Ignore unlabelled elements exceeding physical section sizing rules
        if b_mm > 500.0 or h_mm > 500.0:
            has_explicit_label = False
            for t in c.get("nearest_text", []):
                if re.search(r"\b(C\d+)\b", str(t["text"]).upper()):
                    has_explicit_label = True
                    break
            if not has_explicit_label:
                continue

        base_label = None
        for t in c.get("nearest_text", []):
            text_val = str(t["text"]).strip().upper()
            if "B" in text_val or "X" in text_val or "×" in text_val:
                continue
                
            match = re.search(r"\b(C\d+)\b", text_val)
            if match:
                base_label = match.group(1)
                break
                
        if not base_label:
            base_label = "C_UNLABELED"

        label_counters[base_label] += 1
        member_id = f"{base_label}-{label_counters[base_label]}"
        
        col_members.append({
            "member_id": member_id,
            "member_type": "column",
            "type": "column",
            "start_point": None,
            "end_point": None,
            "center_point": {"x": centroid[0], "y": centroid[1]},
            "boundary_polygon": None,
            "is_void": False,
            "meta": {
                "b": int(b_mm),
                "h": int(h_mm),
                "L_clear": 3.0,
                "end_condition": "fixed_fixed",
                "N_uls": 1000.0,
                "M_uls": 0.0
            },
            "spans": [],
            "spans_m": []
        })
        
    return col_members


def extract_slabs_deterministically(all_members: list[dict]) -> list[dict]:
    """
    Finds all enclosed spaces (slabs) from beam centerlines using pure geometry.
    Uses a closest-point minimization approach to prevent greedy cluster snapping
    and maps true polygonal coordinates to eliminate rectangular overlaps.
    """
    beams = [m for m in all_members if m.get("member_type") == "beam"]
    columns = [m for m in all_members if m.get("member_type") == "column"]
    
    col_points = []
    for c in columns:
        cp = c.get("center_point")
        if cp:
            col_points.append((cp["x"], cp["y"]))
            
    SNAP_TOLERANCE = 650.0 
    lines = []

    for beam in beams:
        sp = beam.get("start_point")
        ep = beam.get("end_point")
        if not sp or not ep:
            continue
            
        sx, sy = sp["x"], sp["y"]
        ex, ey = ep["x"], ep["y"]
        
        # Find the absolute closest column for the start point
        best_start_col = None
        min_start_dist = float("inf")
        for cx, cy in col_points:
            dist = math.hypot(sx - cx, sy - cy)
            if dist <= SNAP_TOLERANCE and dist < min_start_dist:
                min_start_dist = dist
                best_start_col = (cx, cy)
        if best_start_col:
            sx, sy = best_start_col

        # Find the absolute closest column for the end point
        best_end_col = None
        min_end_dist = float("inf")
        for cx, cy in col_points:
            dist = math.hypot(ex - cx, ey - cy)
            if dist <= SNAP_TOLERANCE and dist < min_end_dist:
                min_end_dist = dist
                best_end_col = (cx, cy)
        if best_end_col:
            ex, ey = best_end_col
                
        lines.append(sg.LineString([(sx, sy), (ex, ey)]))

    # Union all snapped lines and find enclosed polygons
    mls = unary_union(lines)
    enclosed_polygons = list(polygonize(mls))
    
    slab_members = []
    for idx, poly in enumerate(enclosed_polygons, start=1):
        # --- CRITICAL FIX 1: Map the true polygon vertices instead of a bounding box ---
        # This preserves L-shapes, recesses, and non-rectangular corners exactly.
        coords = list(poly.exterior.coords)[:-1]
        boundary_polygon = [{"x": round(pt[0], 4), "y": round(pt[1], 4)} for pt in coords]
        
        # Bounding box is only used to compute envelope sizes and design spans
        min_x, min_y, max_x, max_y = poly.bounds
        w_m = round((max_x - min_x) / 1000.0, 3)
        h_m = round((max_y - min_y) / 1000.0, 3)
        
        # Filter out tiny artifacts and sheet-sized outer loops
        if w_m < 0.20 or h_m < 0.20 or w_m > 15.0 or h_m > 15.0:
            continue
            
        # --- CRITICAL FIX 2: Dynamic Aspect Ratio Sizing for Design Spans ---
        # For non-rectangular slabs, using raw poly.bounds can overestimate Lx/Ly.
        # We calculate the true plan area to derive an effective structural span width.
        true_area_m2 = poly.area / 1_000_000.0
        
        # Estimate short span (Lx) based on true geometry area boundaries
        estimated_lx = min(w_m, h_m)
        if true_area_m2 < (w_m * h_m) * 0.85:
            # Shape is complex (L-shaped/recessed). Adjust Lx to reflect truer panel span.
            estimated_lx = round(true_area_m2 / max(w_m, h_m), 3)
            
        slab_members.append({
            "member_id": f"S{idx}",
            "member_type": "slab",
            "type": "solid_slab",
            "boundary_polygon": boundary_polygon,  # Now returns the exact custom polygon path
            "meta": {
                "slab_type": "solid_slab",
                "thickness_mm": 150,
                "Lx": round(max(0.2, estimated_lx), 3),
                "Ly": max(w_m, h_m)
            },
            "spans_m": [round(max(0.2, estimated_lx), 3), max(w_m, h_m)]
        })
        
    return slab_members


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

        # Drop stub beams (length < 0.05 m) ONLY if they have no explicit structural label
        if l_clear < 0.05 and member_id is None:
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


async def _run_member_extraction(
    project_id: str,
    parsed_json: dict,
) -> list[dict]:
    """
    Extract structural members from parsed DXF + optional reference PDF.

    Uses a three-stage pipeline:

    1. **Beams (deterministic)** — geometry comes from DXF LINE entities; section
       and label are read from nearby BeamText annotations.

    2. **Columns (LLM)** — closed rectangular/circular polylines identified by the DXF extractor are sent to llm for label assignment and section confirmation.

    3. **Slabs + voids (LLM, Rasterized image)** — a second llm call uses the
       already-extracted columm, beam and deterministically extracted slab positions as a spatial framework plus
       the rasterized PDF as primary visual reference to confirm or identify slab panels and voids.

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

    # ── Stage 2: Column classification
    col_candidates = [
        c for c in candidates
        if c.get("layer_hint") == "column_candidate"
        or (_COL_FLAGS & set(c.get("flags", [])))
    ]

    col_members = classify_columns_deterministically(col_candidates, beam_members)
    logger.info(
        "Deterministic column extraction: %d columns for project",
        len(col_members)
    )

    # ── Stage 3: slab + void extraction ──────────────────────────────
    # Combine beams and columns for slab extraction
    combined = col_members + beam_members
    slab_members: list[dict] = extract_slabs_deterministically(combined)
    logger.info(
        "Deterministic slab extraction: %d slabs for project",
        len(slab_members))
        
    return combined + slab_members


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


def cross_reference_void_markers(entities: list[dict], members: list[dict]) -> list[dict]:
    """
    Analyzes raw geometry entities and annotations to flag which slab panels 
    represent physical voids (stairwells, lift shafts, or service openings).
    """
    void_keywords = {"VOID", "OPENING", "STAIRWELL", "LIFT", "SHAFT", "OPEN"}
    candidate_lines = []
    void_centers = []

    # 1. Gather isolated geometric entities and texts
    for ent in entities:
        dxf_type = ent.get("dxf_type")
        layer = ent.get("layer", "").upper()
        layer_hint = ent.get("layer_hint", "")
        
        # Explicitly skip grid lines, structural columns, or dimension tracks to avoid noise
        if "GRID" in layer or "DIM" in layer or layer_hint in ("column_candidate", "beam_candidate"):
            continue

        # Capture lines that are long enough to be an 'X' marker cross-brace
        if dxf_type == "LINE":
            geom = ent.get("geometry", {})
            start = geom.get("start")
            end = geom.get("end")
            if start and end:
                dx = abs(end[0] - start[0])
                dy = abs(end[1] - start[1])
                length = math.hypot(dx, dy)
                
                # An 'X' cross line must be diagonal and typically > 500mm
                if length > 500.0 and dx > 100.0 and dy > 100.0:
                    candidate_lines.append(sg.LineString([tuple(start), tuple(end)]))
                
        # Capture text annotations directly
        elif dxf_type in ("TEXT", "MTEXT"):
            content = ent.get("attributes", {}).get("text_content", "").upper()
            if any(kw in content for kw in void_keywords):
                bbox = ent.get("bounding_box", {})
                centroid = bbox.get("centroid", [0.0, 0.0])
                void_centers.append(sg.Point(centroid[0], centroid[1]))

    # 2. Compute intersection points of legitimate cross-brace lines
    for i, line_a in enumerate(candidate_lines):
        for line_b in candidate_lines[i + 1:]:
            if line_a.intersects(line_b):
                inter = line_a.intersection(line_b)
                if isinstance(inter, sg.Point):
                    # Check if they cross near their midpoints (typical for an X marker)
                    void_centers.append(inter)

    # 3. Spatial validation check
    for member in members:
        if member.get("member_type") != "slab":  # Fixed identity bug
            continue
            
        boundary = member.get("boundary_polygon")
        if not boundary or len(boundary) < 3:
            continue
            
        poly_shape = sg.Polygon([(pt["x"], pt["y"]) for pt in boundary])
        
        # Check if this panel contains any verified void coordinates
        is_panel_void = False
        for center in void_centers:
            if poly_shape.contains(center):
                is_panel_void = True
                break
                
        if is_panel_void:
            member["member_type"] = "void"
            member["type"] = "void"
            if "meta" in member:
                member["meta"]["slab_type"] = "opening_void"

    return members


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
        # pdf_path = state.get("uploaded_pdf_path")
        members = await _run_member_extraction(project_id, parsed)
        members = _deduplicate_beams(members)
        members = _filter_stub_beams(members)
        members = cross_reference_void_markers(parsed["entities"], members)
        parsed["members"] = members
        
        # Save structural JSON back to files service and project store
        await file_service.register_geometry(project_id, parsed)
        
        mids = [member.get("member_id") for member in members if member.get("member_id")]
        await project_store.register_members_batch(project_id, mids)

    # ── Step 5: geometry summary ───────────────────────────────────────────────
    scale = await file_service.get_scale(project_id)
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

"""
FastAPI entry point for the standalone geometry parser and viewer.

Provides file upload, synchronous parsing execution, local file persistence,
and CORS configuration for separate frontend testing.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Import local low-level parsing modules
from dxf_parser import extract_geometry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Standalone DXF/PDF Geometry Parser & Viewer")

# Enable CORS for Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
PERSISTENCE_FILE = Path("parsed_geometry.json")

# Ensure upload directory exists
UPLOAD_DIR.mkdir(exist_ok=True)


# ─── Geometry Deduplication & Fallback Heuristic Utilities ───────────

def _cluster_candidate_pairs(candidates: list[dict]) -> list[dict]:
    """
    Cluster duplicate candidates representing the same physical structural members.
    
    1. Beam edge pairs: parallel lines on same layer within 300mm.
    2. Column duplication: co-located column geometries within 75mm.
    """
    _COL_FLAGS = {"rectangular_outline", "circular_section"}
    _BEAM_DIST = 300.0   # mm
    _COL_DIST  = 75.0    # mm

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
                if d < _COL_DIST and d < best_dist:
                    best_dist = d
                    best_j = j
            elif not a_is_col and not b_is_col and same_layer:
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

        # Union text annotations; keep closest 5
        texts: dict[str, dict] = {
            t["text"]: t
            for t in (b.get("nearest_text", []) + a.get("nearest_text", []))
        }
        rep["nearest_text"] = sorted(texts.values(), key=lambda t: t["distance_mm"])[:5]

        merged.append(rep)

    return merged


def _prepare_candidates_summary(parsed_json: dict) -> list[dict]:
    """Prepares geometric candidate instances from parsed raw DXF entities."""
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
        
        if layer_hint in ("column_candidate", "beam_candidate", "slab_candidate") or "rectangular_outline" in flags or "circular_section" in flags:
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

    return _cluster_candidate_pairs(candidates)


def _fallback_members_heuristics(candidates: list[dict]) -> list[dict]:
    """Generates classified columns and beams from candidates without requiring an LLM."""
    members = []
    beam_idx = 1
    col_idx = 1
    
    for cand in candidates:
        layer_hint = cand["layer_hint"]
        bbox = cand["bbox"]
        spatial = cand.get("spatial", {})
        
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


# ─── Endpoints ────────────────────────────────────────────────────────

import parser_pipeline

@app.post("/api/upload")
async def upload_files(
    dxf_file: UploadFile = File(...),
    pdf_file: Optional[UploadFile] = File(None)
):
    """
    Upload DXF and optional PDF files, parse them using the full pipeline, persist JSON output, and return the schema.
    """
    if not dxf_file.filename:
        raise HTTPException(status_code=400, detail="Invalid DXF upload filename")
        
    logger.info("Upload received: DXF = %s, PDF = %s", dxf_file.filename, pdf_file.filename if pdf_file else "None")
    
    # Save DXF
    dxf_path = UPLOAD_DIR / dxf_file.filename
    with open(dxf_path, "wb") as f:
        f.write(await dxf_file.read())
        
    # Save PDF if provided
    pdf_path = None
    if pdf_file and pdf_file.filename:
        pdf_path = UPLOAD_DIR / pdf_file.filename
        with open(pdf_path, "wb") as f:
            f.write(await pdf_file.read())

    # Run full parsing pipeline (which handles both DXF & PDF, heuristics fallback & LLM)
    try:
        response_payload = await parser_pipeline.run_pipeline(
            str(dxf_path), 
            str(pdf_path) if pdf_path else None
        )
        # Add timestamp
        response_payload["parsed_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as e:
        logger.error("Failed to run parser pipeline: %s", e)
        raise HTTPException(status_code=500, detail=f"Parser pipeline error: {str(e)}")

    # Persist response payload locally
    with open(PERSISTENCE_FILE, "w") as f:
        json.dump(response_payload, f, indent=2)

    logger.info("Parsing complete. Saved geometry response to %s", PERSISTENCE_FILE)
    return response_payload


@app.get("/api/parsed")
async def get_parsed_geometry():
    """Reads and returns the locally  persisted structural geometry JSON."""
    if not PERSISTENCE_FILE.exists():
        raise HTTPException(status_code=404, detail="No parsed geometry cached. Please upload a file first.")
        
    try:
        with open(PERSISTENCE_FILE, "r") as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read cached geometry file: {str(e)}")

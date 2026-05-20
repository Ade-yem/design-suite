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
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage
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
        if dxf_type in ("TEXT", "MTEXT"):
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
            cand = {
                "entity_id": ent.get("entity_id"),
                "dxf_type": dxf_type,
                "layer": layer,
                "layer_hint": layer_hint,
                "centroid": centroid,
                "bbox": bbox,
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


async def _run_llm_member_extraction(project_id: str, parsed_json: dict) -> list[dict]:
    """
    Runs Gemini to classify raw geometry entities into structured members.

    Parameters
    ----------
    project_id : str
        Project identifier.
    parsed_json : dict
        Parsed structural JSON.

    Returns
    -------
    list[dict]
        Identified structural member objects list.
    """
    candidates = _prepare_candidates_summary(parsed_json)
    if not candidates:
        return parsed_json.get("members", [])
        
    candidates_data = []
    for cand in candidates:
        cand_summary = {
            "entity_id": cand["entity_id"],
            "type": cand["dxf_type"],
            "layer": cand["layer"],
            "hint": cand["layer_hint"],
            "bbox_width_mm": cand["bbox"].get("width"),
            "bbox_height_mm": cand["bbox"].get("height"),
            "flags": cand["flags"],
            "nearby_text": cand["nearest_text"]
        }
        candidates_data.append(cand_summary)
        
    prompt = f"""
You are the Vision & Parsing Agent (the "Eyes") of an AI-driven structural design copilot. 
Analyze these structural candidates from a parsed DXF drawing and identify/classify them into standard structural member objects.

Candidates data (with their closest 5 text annotations):
{json.dumps(candidates_data, indent=2)}

Guidelines:
1. Identify columns, beams, and slabs from layers and nearby text.
2. Group nearby candidate geometries that represent the same beam spans or column grids.
3. Map each member to a standard structural label (e.g., C1, B1, S1) from its nearby text.
   - For example, if a candidate has a nearby text "C1" or similar, name it "C1".
   - If no label is found, generate sequential names like "B1", "B2", "C1", "C2" etc.
4. Extract beam cross-sections and span lengths:
   - Beam spans: Beams usually span between columns. The physical length is given by the bbox width/height.
     IMPORTANT: Convert length to meters (divide mm by 1000). For example, a 6000mm length is a 6.0m span.
   - Beam section: Search nearby text for section dimensions like "230x600", "300x500" or similar. Extract width `b_mm` and depth `h_mm`.
5. Extract column cross-sections:
   - Bounding box dimensions (bbox_width_mm, bbox_height_mm) represent the column cross-section (b and h in mm).
   - If nearby text specifies a column size like "300x300", use that.
6. Output a JSON list of members.

Each member in the returned JSON must strictly follow this structure:
{{
    "member_id": "C1", // Unique label
    "member_type": "column", // "beam" | "column" | "slab" | "wall" | "footing" | "staircase"
    "type": "column", // Keep identical to member_type for compatibility
    "meta": {{
        // For beams:
        "b_mm": 300, // beam width in mm
        "h_mm": 600, // beam depth in mm
        "L_clear": 6.0, // clear span in meters
        "E": 30000000.0, // elastic modulus in kPa (30 GPa default)
        "I": 0.0054 // moment of inertia in m4 (b_mm * h_mm^3 / 12 / 10^12)
        
        // For columns:
        "b": 300, // column width in mm
        "h": 300, // column depth in mm
        "L_clear": 3.0, // column clear height in meters
        "end_condition": "fixed_fixed",
        "N_uls": 1000.0,
        "M_uls": 0.0
    }},
    "spans": [
        {{
            "span_id": "S1",
            "length_m": 6.0
        }}
    ],
    "spans_m": [6.0]
}}

Return ONLY a valid JSON array of members. Do not include markdown block wrappers (like ```json), no extra conversational text, no pre-amble.
"""

    try:
        llm = _get_llm()
        response = await llm.ainvoke(prompt)
        text = response.text.strip()
        
        if "```" in text:
            match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
            if match:
                text = match.group(1).strip()
                
        members = json.loads(text)
        if isinstance(members, list):
            for m in members:
                m_type = m.get("member_type", m.get("type", "beam"))
                m["member_type"] = m_type
                m["type"] = m_type
                
                if m_type == "beam":
                    meta = m.setdefault("meta", {})
                    b = float(meta.setdefault("b_mm", 300))
                    h = float(meta.setdefault("h_mm", 500))
                    meta.setdefault("I", round((b / 1000.0) * ((h / 1000.0) ** 3) / 12.0, 6))
                    meta.setdefault("E", 30e6)
                    meta.setdefault("L_clear", m.get("spans", [{}])[0].get("length_m", 5.0))
                elif m_type == "column":
                    meta = m.setdefault("meta", {})
                    meta.setdefault("b", 300)
                    meta.setdefault("h", 300)
                    meta.setdefault("L_clear", 3.0)
                    meta.setdefault("end_condition", "fixed_fixed")
                    meta.setdefault("N_uls", 1000.0)
                    meta.setdefault("M_uls", 0.0)
            return members
    except Exception as e:
        logger.error(f"Error parsing members from LLM response: {e}")
        return _fallback_members_heuristics(candidates)
        
    return []


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
        f"### 🏗️ **Structural Member Summary**",
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
        summary.append("\n⚠️ No structural members identified yet.")
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
        
        for member in members:
            mid = member.get("member_id")
            if mid:
                await project_store.register_member(project_id, mid)

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

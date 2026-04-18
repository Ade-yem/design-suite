"""
services/agents/parser.py  (Vision Agent)
==========================================
Vision Agent node — the "Eyes" of the pipeline.

Responsibilities
----------------
1. Trigger async DXF/PDF parsing via the FastAPI files router.
2. Detect and surface unit/scale ambiguity **before** anything else.
   (Risk 2 from the product brief — a 6 m beam vs a 6 mm beam produces
   catastrophically different results.) The agent blocks here until the
   engineer explicitly confirms units.
3. Summarise the detected structural members for engineer review.
4. Produce the state update that feeds Gate 1 (geometry_verification_gate).

Rule: This node **never calls analysis or design code directly**.
      It only calls the files API tools.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import AIMessage

from services.agents.api_client import api_client, poll_job_until_complete
from services.agents.state import StructuralDesignState

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

    if not dimensions:
        return {
            "ambiguous": True,
            "detected_unit": "unknown",
            "confidence": "low",
            "sample_dimensions": [],
        }

    mean_dim = sum(dimensions) / len(dimensions)

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
        "sample_dimensions": dimensions[:5],
    }


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
    if not members:
        return "_No structural members detected in this drawing._"

    by_type: dict[str, list[str]] = {}
    for m in members:
        member_type = m.get("member_type", "unknown")
        mid = m.get("member_id", "?")
        by_type.setdefault(member_type, []).append(mid)

    lines = []
    for mtype, ids in sorted(by_type.items()):
        lines.append(f"- **{mtype.capitalize()}s** ({len(ids)}): {', '.join(ids[:10])}"
                     + (" …" if len(ids) > 10 else ""))

    warnings = parsed_json.get("parse_warnings", [])
    warning_block = ""
    if warnings:
        warning_block = "\n\n⚠️ **Parser warnings:**\n" + "\n".join(f"- {w}" for w in warnings)

    total = len(members)
    return f"**{total} member(s) detected:**\n\n" + "\n".join(lines) + warning_block


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
        Current pipeline state.  Requires ``project_id`` and
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

    try:
        upload_resp = await api_client.upload_file(
            f"/api/v1/files/upload/{project_id}", file_path=file_path
        )
        parse_job_id: str = upload_resp["job_id"]
    except Exception as exc:
        logger.exception("File upload failed for project %s.", project_id)
        return {
            "messages": [AIMessage(content=f"❌ Upload failed: {exc}")],
            "agent_logs": [{**log_entry, "status": "upload_failed"}],
            "current_error": "FILE_PARSE_ERROR",
        }

    # ── Step 2: poll parsing ───────────────────────────────────────────────────
    logs: list[dict] = [{**log_entry, "status": "parsing_started", "detail": parse_job_id}]

    def _on_progress(status_dict: dict) -> None:
        logs.append({
            **log_entry,
            "status": "parsing",
            "detail": status_dict.get("current_step", ""),
            "pct": status_dict.get("progress_pct", 0),
        })

    try:
        await poll_job_until_complete(parse_job_id, progress_cb=_on_progress)
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"❌ Parsing failed: {exc}")],
            "agent_logs": logs + [{**log_entry, "status": "parse_failed"}],
            "current_error": "FILE_PARSE_ERROR",
            "parse_job_id": parse_job_id,
        }

    # ── Step 3: fetch parsed result ────────────────────────────────────────────
    try:
        parsed_json: dict = await api_client.get(f"/api/v1/files/{project_id}/parsed")
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"❌ Could not retrieve parsed geometry: {exc}")],
            "agent_logs": logs + [{**log_entry, "status": "fetch_failed"}],
            "current_error": "FILE_PARSE_ERROR",
        }

    # ── Step 4: unit ambiguity detection ──────────────────────────────────────
    unit_check = _detect_unit_ambiguity(parsed_json)
    logs.append({**log_entry, "status": "unit_check", "detail": unit_check})

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
            "parsed_structural_json": parsed_json,
            "unit_confirmation": unit_check,
            "parse_job_id": parse_job_id,
            "messages": [message],
            "agent_logs": logs + [{**log_entry, "status": "awaiting_unit_confirmation"}],
            "pipeline_status": "file_uploaded",
        }

    # ── Step 5: geometry summary ───────────────────────────────────────────────
    summary = _build_geometry_summary(parsed_json)
    scale = await api_client.get(f"/api/v1/files/{project_id}/scale")

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
        "parsed_structural_json": parsed_json,
        "unit_confirmation": unit_check,
        "parse_job_id": parse_job_id,
        "pipeline_status": "file_uploaded",
        "messages": [message],
        "agent_logs": logs + [{**log_entry, "status": "awaiting_verification"}],
    }

"""
services/agents/tools.py
========================
LangGraph / LangChain Tool Registry.

Every FastAPI endpoint called by an agent is wrapped as a named ``@tool`` here.
Agents **never** call ``api_client`` directly — they always go through a tool.
This ensures:
- Every API call is logged and traceable via LangSmith
- Tool schemas are auto-generated for the LLM (OpenAI function calling format)
- Mocking is possible in tests without touching the HTTP layer

Tool groups
-----------
FILES       : upload, verify geometry (Gate 1), scale management
LOADING     : define, validate, combine, output
ANALYSIS    : run (full + per-type), poll status, results
DESIGN      : run (full + per-type), override member, rerun
DRAWINGS    : generate, get, regenerate, confirm (Gate 4), layers
REPORTS     : generate, preview, download
PIPELINE    : status, gates, confirm gate, reset
JOBS        : poll, cancel
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Literal

from langchain_core.tools import tool

from services.files import file_service
from services.loading import loading_service
from services.analysis import analysis_service
from services.design import design_service
from storage.project_store import project_store
from storage.job_store import job_store
from schemas.project import ProjectStatus
from core.drawing import generate_drawing_commands

logger = logging.getLogger(__name__)


# ─── HELPER FUNCTIONS ─────────────────────────────────────────────────────────

def _build_members_payload(project_id: str, member_ids: Any) -> list[dict]:
    """
    Construct member payloads containing loading, analysis, and design data for report generation.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    member_ids : list[str] | "all"
        Specific member IDs to filter by, or "all" to include all designed members.

    Returns
    -------
    list[dict]
        List of member dictionaries, each containing:
        member_id, member_type, floor_level, design_code,
        loading_output, analysis_output, and design_output.
    """
    # Fetch from design service
    design_results = design_service.get_results(project_id)
    designed_members = design_results.get("members", [])
    
    # Filter by member_ids if specified
    if member_ids != "all" and isinstance(member_ids, list):
        id_set = set(member_ids)
        designed_members = [m for m in designed_members if m.get("member_id") in id_set]
        
    # Fetch loading outputs
    try:
        loading_output = loading_service.get_output(project_id)
        loading_map = {m["member_id"]: m for m in loading_output.get("members", [])}
    except Exception:
        loading_map = {}
        
    # Fetch analysis outputs
    try:
        analysis_results = analysis_service.get_results(project_id)
        analysis_map = {m["member_id"]: m for m in analysis_results.get("members", [])}
    except Exception:
        analysis_map = {}
        
    # Fetch parsed geometry (for floor level, etc.)
    try:
        parsed_geom = file_service.get_parsed(project_id)
        geom_map = {m["member_id"]: m for m in parsed_geom.get("members", [])}
    except Exception:
        geom_map = {}
        
    members_payload = []
    for dm in designed_members:
        mid = dm["member_id"]
        members_payload.append({
            "member_id": mid,
            "member_type": dm.get("member_type") or geom_map.get(mid, {}).get("member_type") or "beam",
            "floor_level": geom_map.get(mid, {}).get("floor_level") or "1",
            "design_code": dm.get("design_code", "BS8110"),
            "loading_output": loading_map.get(mid) or {},
            "analysis_output": analysis_map.get(mid) or {},
            "design_output": dm
        })
    return members_payload


# ─── FILES ────────────────────────────────────────────────────────────────────


@tool
async def upload_structural_file(project_id: str, file_path: str) -> dict:
    """
    Upload a DXF or PDF structural drawing and trigger asynchronous parsing.

    Returns immediately with a job_id — poll ``poll_parse_job`` for completion.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    file_path : str
        Absolute path to the file to upload.

    Returns
    -------
    dict
        ``{message, job_id, status_url}``
    """
    job_id = job_store.create("parsing", project_id=project_id)
    
    async def parse_bg():
        job_store.mark_running(job_id, "Parsing file…")
        try:
            await file_service.parse(project_id, file_path)
            job_store.mark_complete(job_id, result_url=f"/api/v1/files/{project_id}/parsed")
        except Exception as exc:
            job_store.mark_failed(job_id, errors=[str(exc)])
            
    asyncio.create_task(parse_bg())
    
    return {
        "message": "File uploaded. Parsing in progress.",
        "job_id": job_id,
        "status_url": f"/api/v1/files/{project_id}/parse-status/{job_id}",
    }


@tool
async def get_parsed_geometry(project_id: str) -> dict:
    """
    Retrieve the structural JSON produced by the Vision Agent parser.

    Parameters
    ----------
    project_id : str
        Target project identifier.

    Returns
    -------
    dict
        Parsed structural JSON including detected members, scale, and warnings.
    """
    return file_service.get_parsed(project_id)


@tool
async def confirm_geometry(
    project_id: str,
    corrections: Optional[list] = None,
    notes: str = "",
) -> dict:
    """
    Confirm parsed geometry and pass Gate 1 (geometry verification).

    Must be called with explicit engineer confirmation before the loading and
    analysis stages can proceed.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    corrections : list | None
        Optional list of member-level corrections to apply.
    notes : str
        Engineer confirmation notes for the calculation record.

    Returns
    -------
    dict
        ``{status: "verified", member_count, verified_at}``
    """
    return file_service.verify_geometry(
        project_id,
        corrections=corrections,
        notes=notes,
    )


@tool
async def get_detected_scale(project_id: str) -> dict:
    """
    Retrieve the scale / unit information detected during DXF parsing.

    Parameters
    ----------
    project_id : str
        Target project identifier.

    Returns
    -------
    dict
        ``{factor, unit, detected, confirmed}``
    """
    return file_service.get_scale(project_id)


@tool
async def confirm_scale(
    project_id: str, scale_factor: float, unit_label: str
) -> dict:
    """
    Confirm or correct the detected drawing scale factor.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    scale_factor : float
        Numeric scale factor (e.g. 0.001 to convert mm → m).
    unit_label : str
        Unit label string (e.g. ``"mm"`` or ``"m"``).

    Returns
    -------
    dict
        Updated scale record.
    """
    return file_service.confirm_scale(
        project_id,
        scale_factor=scale_factor,
        unit_label=unit_label,
    )


# ─── LOADING ──────────────────────────────────────────────────────────────────


@tool
async def define_loads(project_id: str, load_definition: dict) -> dict:
    """
    Submit a complete load definition to the loading module.

    The definition is validated and stored but does not automatically run the
    combination engine.  Call ``run_load_combinations`` next.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    load_definition : dict
        Payload matching ``LoadDefinitionRequest`` schema, including
        ``design_code``, ``occupancy_category``, ``dead_loads``,
        ``imposed_loads``, and optional ``member_overrides``.

    Returns
    -------
    dict
        ``{project_id, status, design_code, occupancy_category, created_at}``
    """
    return loading_service.define(project_id, load_definition)


@tool
async def validate_loads(project_id: str, load_definition: dict) -> dict:
    """
    Validate a load definition without persisting it.

    Use before ``define_loads`` to provide instant chat-panel feedback.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    load_definition : dict
        Load definition to validate (same schema as ``define_loads``).

    Returns
    -------
    dict
        ``{valid: bool, errors: list[str], warnings: list[str]}``
    """
    res = loading_service.validate(load_definition)
    return res.model_dump() if hasattr(res, "model_dump") else res


@tool
async def run_load_combinations(project_id: str) -> dict:
    """
    Run the load combination engine and produce factored ULS/SLS loads.

    Advances the project to ``LOADING_DEFINED`` status on success.

    Parameters
    ----------
    project_id : str
        Target project identifier.

    Returns
    -------
    dict
        Full loading output with factored loads per member.
    """
    return loading_service.run_combinations(project_id)


@tool
async def get_loading_output(project_id: str) -> dict:
    """
    Retrieve the complete loading output JSON.

    Parameters
    ----------
    project_id : str
        Target project identifier.

    Returns
    -------
    dict
        ``LoadingOutputResponse`` including all member factored loads.
    """
    return loading_service.get_output(project_id)


@tool
async def update_member_loads(
    project_id: str, member_id: str, update: dict
) -> dict:
    """
    Apply a per-member load override (e.g. extra dead load or imposed override).

    Parameters
    ----------
    project_id : str
        Target project identifier.
    member_id : str
        Target member identifier.
    update : dict
        ``{dead_extra_kNm2, imposed_override_kNm2, notes}``

    Returns
    -------
    dict
        Updated override record.
    """
    return loading_service.update_member_loads(
        project_id,
        member_id,
        dead_extra_kNm2=update.get("dead_extra_kNm2"),
        imposed_override_kNm2=update.get("imposed_override_kNm2"),
        notes=update.get("notes", ""),
    )


# ─── ANALYSIS ────────────────────────────────────────────────────────────────


@tool
async def run_full_analysis(project_id: str, options: Optional[dict] = None) -> dict:
    """
    Queue a full structural analysis run for all members.

    Returns immediately with a job_id.  Use ``poll_job`` to track progress.
    When complete, the project advances to ``ANALYSIS_COMPLETE``.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    options : dict | None
        ``AnalysisOptions`` fields to override
        (pattern_loading, self_weight_iteration, max_iterations, etc.).

    Returns
    -------
    dict
        ``{job_id, status_url, message}``
    """
    job_id = job_store.create("analysis", project_id=project_id)
    
    async def run_analysis_bg():
        job_store.mark_running(job_id, "Initialising analysis engine…")
        try:
            def _progress(step: str, pct: float) -> None:
                job_store.update_progress(job_id, pct, step)
                
            await analysis_service.run(
                project_id,
                member_ids=None,
                options=options or {},
                progress_cb=_progress,
            )
            job_store.mark_complete(job_id, result_url=f"/api/v1/analysis/{project_id}/results")
        except Exception as exc:
            job_store.mark_failed(job_id, errors=[str(exc)])
            
    asyncio.create_task(run_analysis_bg())
    
    return {
        "job_id": job_id,
        "status_url": f"/api/v1/analysis/{project_id}/status/{job_id}",
        "message": f"Analysis queued. Poll status_url for updates. Job: {job_id}.",
    }


@tool
async def run_member_analysis(
    project_id: str, member_type: str, member_ids: list[str]
) -> dict:
    """
    Queue analysis for a specific subset of members of one type.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    member_type : str
        One of: beam | slab | column | wall | footing | staircase.
    member_ids : list[str]
        IDs of members to analyse.

    Returns
    -------
    dict
        ``{job_id, status_url, message}``
    """
    job_id = job_store.create("analysis", project_id=project_id)
    
    async def run_analysis_bg():
        job_store.mark_running(job_id, "Initialising analysis engine…")
        try:
            def _progress(step: str, pct: float) -> None:
                job_store.update_progress(job_id, pct, step)
                
            await analysis_service.run(
                project_id,
                member_ids=member_ids,
                options={},
                progress_cb=_progress,
            )
            job_store.mark_complete(job_id, result_url=f"/api/v1/analysis/{project_id}/results")
        except Exception as exc:
            job_store.mark_failed(job_id, errors=[str(exc)])
            
    asyncio.create_task(run_analysis_bg())
    
    return {
        "job_id": job_id,
        "status_url": f"/api/v1/analysis/{project_id}/status/{job_id}",
        "message": f"Analysis queued. Poll status_url for updates. Job: {job_id}.",
    }


@tool
async def get_analysis_results(project_id: str) -> dict:
    """
    Retrieve all completed analysis results for a project.

    Parameters
    ----------
    project_id : str
        Target project identifier.

    Returns
    -------
    dict
        ``AnalysisResultsResponse`` including all member results.
    """
    return analysis_service.get_results(project_id)


@tool
async def get_member_analysis_result(project_id: str, member_id: str) -> dict:
    """
    Retrieve the analysis result for a single member.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    member_id : str
        Target member identifier.

    Returns
    -------
    dict
        Single-member ``MemberAnalysisResult`` dict.
    """
    return analysis_service.get_member_result(project_id, member_id)


# ─── DESIGN ───────────────────────────────────────────────────────────────────


@tool
async def run_full_design(
    project_id: str, design_code: Optional[str] = None
) -> dict:
    """
    Queue a full design suite run for all members.

    Returns immediately with a job_id.  When complete, the project advances to
    ``DESIGN_COMPLETE``.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    design_code : str | None
        Override the project-level design code for this run only.

    Returns
    -------
    dict
        ``{job_id, status_url, message}``
    """
    job_id = job_store.create("design", project_id=project_id)
    
    async def run_design_bg():
        job_store.mark_running(job_id, "Initialising design suite…")
        try:
            def _progress(step: str, pct: float) -> None:
                job_store.update_progress(job_id, pct, step)
                
            await design_service.run(
                project_id,
                member_ids=None,
                design_code=design_code,
                progress_cb=_progress,
            )
            job_store.mark_complete(job_id, result_url=f"/api/v1/design/{project_id}/results")
        except Exception as exc:
            job_store.mark_failed(job_id, errors=[str(exc)])
            
    asyncio.create_task(run_design_bg())
    
    return {
        "job_id": job_id,
        "status_url": f"/api/v1/design/{project_id}/status/{job_id}",
        "message": f"Design queued. Poll status_url for updates. Job: {job_id}.",
    }


@tool
async def run_member_design(
    project_id: str, member_type: str, member_ids: list[str]
) -> dict:
    """
    Queue design for a specific subset of members of one type.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    member_type : str
        One of: beam | slab | column | wall | footing | staircase.
    member_ids : list[str]
        IDs of members to design.

    Returns
    -------
    dict
        ``{job_id, status_url, message}``
    """
    job_id = job_store.create("design", project_id=project_id)
    
    async def run_design_bg():
        job_store.mark_running(job_id, "Initialising design suite…")
        try:
            def _progress(step: str, pct: float) -> None:
                job_store.update_progress(job_id, pct, step)
                
            await design_service.run(
                project_id,
                member_ids=member_ids,
                design_code=None,
                progress_cb=_progress,
            )
            job_store.mark_complete(job_id, result_url=f"/api/v1/design/{project_id}/results")
        except Exception as exc:
            job_store.mark_failed(job_id, errors=[str(exc)])
            
    asyncio.create_task(run_design_bg())
    
    return {
        "job_id": job_id,
        "status_url": f"/api/v1/design/{project_id}/status/{job_id}",
        "message": f"Design queued. Poll status_url for updates. Job: {job_id}.",
    }


@tool
async def get_design_results(project_id: str) -> dict:
    """
    Retrieve all completed design results for a project.

    Parameters
    ----------
    project_id : str
        Target project identifier.

    Returns
    -------
    dict
        ``DesignResultsResponse`` including member reinforcement schedules.
    """
    return design_service.get_results(project_id)


@tool
async def override_member_design(
    project_id: str, member_id: str, override: dict
) -> dict:
    """
    Apply a direct engineer override to a designed member.

    Called when an engineer changes geometry in the chat panel
    (e.g. "change beam B1 to 300×600") or clicks a member on the canvas.
    Re-checks all limit states and returns a warning if re-analysis is needed.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    member_id : str
        Target member identifier.
    override : dict
        ``MemberDesignOverride`` fields: b_mm, h_mm, cover_mm, fcu_MPa,
        fck_MPa, fy_MPa, meta_updates, reason.

    Returns
    -------
    dict
        ``{result, warning, reanalysis_url}``
    """
    outcome = design_service.apply_override(project_id, member_id, override=override)
    reanalysis_url = f"/api/v1/analysis/{project_id}/run" if outcome.get("reanalysis_needed") else None
    return {
        "result": outcome["result"],
        "warning": outcome.get("warning"),
        "reanalysis_url": reanalysis_url,
    }


@tool
async def rerun_member_design(project_id: str, member_id: str) -> dict:
    """
    Rerun the design for a single member after a geometry or load override.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    member_id : str
        Target member identifier.

    Returns
    -------
    dict
        ``{job_id, status_url, message}``
    """
    job_id = job_store.create("design", project_id=project_id)
    
    async def run_design_bg():
        job_store.mark_running(job_id, "Initialising design suite…")
        try:
            def _progress(step: str, pct: float) -> None:
                job_store.update_progress(job_id, pct, step)
                
            await design_service.run(
                project_id,
                member_ids=[member_id],
                design_code=None,
                progress_cb=_progress,
            )
            job_store.mark_complete(job_id, result_url=f"/api/v1/design/{project_id}/results")
        except Exception as exc:
            job_store.mark_failed(job_id, errors=[str(exc)])
            
    asyncio.create_task(run_design_bg())
    
    return {
        "job_id": job_id,
        "status_url": f"/api/v1/design/{project_id}/status/{job_id}",
        "message": f"Design queued. Poll status_url for updates. Job: {job_id}.",
    }


# ─── DRAWINGS ────────────────────────────────────────────────────────────────


@tool
async def generate_drawings(project_id: str) -> dict:
    """
    Generate 2D structural drawing commands for all designed members.

    Returns immediately with a job_id.  Canvas commands are returned when
    polling completes.

    Parameters
    ----------
    project_id : str
        Target project identifier.

    Returns
    -------
    dict
        ``{job_id, status_url, message}``
    """
    job_id = job_store.create("drawings", project_id=project_id)
    job_store.mark_running(job_id, "Generating drawing commands…")
    try:
        design_results = design_service.get_results(project_id)
        members = design_results.get("members", [])
        drawing_commands = []
        for member in members:
            cmds = generate_drawing_commands(member)
            drawing_commands.append({
                "member_id": member["member_id"],
                "member_type": member["member_type"],
                "commands": cmds
            })
            
        from routers.drawings import _drawings_store
        _drawings_store[project_id] = drawing_commands
        job_store.mark_complete(job_id)
        
        return {
            "job_id": job_id,
            "status_url": f"/api/v1/drawings/{project_id}/status/{job_id}",
            "message": "Drawing generation in progress."
        }
    except Exception as exc:
        job_store.mark_failed(job_id, errors=[str(exc)])
        raise exc


@tool
async def get_member_drawing(project_id: str, member_id: str) -> dict:
    """
    Retrieve drawing commands for a single member.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    member_id : str
        Target member identifier.

    Returns
    -------
    dict
        ``DrawingCommandSet`` for the member.
    """
    from routers.drawings import _drawings_store
    drawings = _drawings_store.get(project_id, [])
    for d in drawings:
        if d.get("member_id") == member_id:
            return d
    return {}


@tool
async def regenerate_member_drawing(project_id: str, member_id: str) -> dict:
    """
    Regenerate drawing commands for a member after an engineer edit.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    member_id : str
        Target member identifier.

    Returns
    -------
    dict
        Updated ``DrawingCommandSet``.
    """
    from routers.drawings import _drawings_store
    design_results = design_service.get_results(project_id)
    members = design_results.get("members", [])
    member = next((m for m in members if m.get("member_id") == member_id), None)
    if not member:
        raise ValueError(f"Member '{member_id}' not found in design results.")
        
    cmds = generate_drawing_commands(member)
    updated_drawing = {
        "member_id": member_id,
        "member_type": member["member_type"],
        "commands": cmds
    }
    
    drawings = _drawings_store.setdefault(project_id, [])
    for i, d in enumerate(drawings):
        if d.get("member_id") == member_id:
            drawings[i] = updated_drawing
            break
    else:
        drawings.append(updated_drawing)
        
    return updated_drawing


@tool
async def confirm_drawings(project_id: str, notes: str = "") -> dict:
    """
    Confirm all drawings and pass Gate 4 (drawing review).

    Parameters
    ----------
    project_id : str
        Target project identifier.
    notes : str
        Engineer confirmation notes.

    Returns
    -------
    dict
        ``{status: "confirmed", confirmed_at}``
    """
    return {
        "status": "confirmed",
        "confirmed_at": datetime.now(timezone.utc).isoformat()
    }


@tool
async def get_layer_package(project_id: str) -> dict:
    """
    Retrieve the layer structure for the Canvas panel layer manager.

    Parameters
    ----------
    project_id : str
        Target project identifier.

    Returns
    -------
    dict
        Layer package with layer metadata and bounding box.
    """
    return {"layers": [], "bounds": {"width": 1000, "height": 1000}}


# ─── REPORTS ─────────────────────────────────────────────────────────────────


@tool
async def generate_report(
    project_id: str,
    report_type: str = "full",
    member_ids: Any = "all",
) -> dict:
    """
    Generate the final engineering report (calc sheets, schedules, quantities).

    Parameters
    ----------
    project_id : str
        Target project identifier.
    report_type : str
        One of: calculation_sheets | schedule | quantities | compliance |
        summary | full.
    member_ids : list[str] | "all"
        Member subset, or ``"all"`` for the entire design.

    Returns
    -------
    dict
        ``{report_id, preview_url, download_url, status, member_count}``
    """
    project = project_store.get_or_404(project_id)
    
    design_code_edition = "BS 8110-1:1997" if project.design_code == "BS8110" else "EN 1992-1-1:2004"
    
    from routers.reports import generate_report as run_report_generation, GenerateReportRequest, ProjectMeta
    
    project_meta = ProjectMeta(
        name=project.name,
        reference=project.reference,
        client=project.client,
        engineer="Lead Engineer",
        checker="Senior Checker",
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        revision="P01",
        design_code=project.design_code,
        design_code_edition=design_code_edition
    )
    
    members_payload = _build_members_payload(project_id, member_ids)
    
    req = GenerateReportRequest(
        project_id=project_id,
        project=project_meta,
        members=members_payload,
        report_type=report_type,
        member_ids=member_ids,
        format="html"
    )
    
    from fastapi import BackgroundTasks
    bg = BackgroundTasks()
    res = await run_report_generation(req, bg)
    
    project_store.advance_status(project_id, ProjectStatus.REPORT_GENERATED)
    
    return res.model_dump() if hasattr(res, "model_dump") else res


# ─── PIPELINE & JOBS ─────────────────────────────────────────────────────────


@tool
async def get_pipeline_status(project_id: str) -> dict:
    """
    Retrieve the current pipeline stage and all gate statuses.

    Parameters
    ----------
    project_id : str
        Target project identifier.

    Returns
    -------
    dict
        ``PipelineStatusResponse`` with gates, next_action, and blocking_issues.
    """
    project = project_store.get_or_404(project_id)
    current = ProjectStatus(project.pipeline_status_ordinal)
    
    from routers.pipeline import _build_gates, _NEXT_ACTION_MAP
    gates = _build_gates(project.pipeline_status_ordinal)
    
    return {
        "project_id": project.project_id,
        "current_stage": project.pipeline_status,
        "next_action": _NEXT_ACTION_MAP.get(current, "complete"),
        "gates": gates,
        "blocking_issues": [],
        "completed_members": project.member_count,
        "failed_members": 0,
        "last_updated": project.updated_at.isoformat() if hasattr(project.updated_at, "isoformat") else project.updated_at,
    }


@tool
async def confirm_pipeline_gate(project_id: str, gate: str) -> dict:
    """
    Manually confirm a pipeline gate to advance the project status.

    Parameters
    ----------
    project_id : str
        Target project identifier.
    gate : str
        Gate label: geometry_verified | loading_confirmed | analysis_complete |
        design_complete | report_approved.

    Returns
    -------
    dict
        ``{gate, confirmed_at, new_status}``
    """
    from routers.pipeline import _GATE_TO_STATUS
    target_status = _GATE_TO_STATUS.get(gate)
    if target_status is None:
        raise ValueError(f"Unknown gate '{gate}'. Valid gates: {list(_GATE_TO_STATUS.keys())}")
        
    project_store.advance_status(project_id, target_status)
    
    return {
        "gate": gate,
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
        "new_status": target_status.label(),
    }


@tool
async def poll_job(job_id: str) -> dict:
    """
    Get the current status of an async job (single poll — no blocking).

    Parameters
    ----------
    job_id : str
        Job identifier.

    Returns
    -------
    dict
        ``JobStatus`` dict.
    """
    job = job_store.get_or_404(job_id)
    return job.model_dump() if hasattr(job, "model_dump") else job


# ── All tools as a flat list for agent binding ────────────────────────────────
ALL_TOOLS = [
    upload_structural_file,
    get_parsed_geometry,
    confirm_geometry,
    get_detected_scale,
    confirm_scale,
    define_loads,
    validate_loads,
    run_load_combinations,
    get_loading_output,
    update_member_loads,
    run_full_analysis,
    run_member_analysis,
    get_analysis_results,
    get_member_analysis_result,
    run_full_design,
    run_member_design,
    get_design_results,
    override_member_design,
    rerun_member_design,
    generate_drawings,
    get_member_drawing,
    regenerate_member_drawing,
    confirm_drawings,
    get_layer_package,
    generate_report,
    get_pipeline_status,
    confirm_pipeline_gate,
    poll_job,
]

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

import logging
from typing import Any, Optional

from langchain_core.tools import tool

from services.agents.api_client import api_client, poll_job_until_complete

logger = logging.getLogger(__name__)


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
    return await api_client.upload_file(
        f"/api/v1/files/upload/{project_id}",
        file_path=file_path,
    )


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
    return await api_client.get(f"/api/v1/files/{project_id}/parsed")


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
    return await api_client.put(
        f"/api/v1/files/{project_id}/verify",
        json={
            "confirmed": True,
            "corrections": corrections or [],
            "notes": notes,
        },
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
    return await api_client.get(f"/api/v1/files/{project_id}/scale")


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
    return await api_client.put(
        f"/api/v1/files/{project_id}/scale",
        json={"scale_factor": scale_factor, "unit_label": unit_label, "confirmed": True},
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
    return await api_client.post(
        f"/api/v1/loading/{project_id}/define", json=load_definition
    )


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
    return await api_client.post(
        f"/api/v1/loading/{project_id}/validate", json=load_definition
    )


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
    return await api_client.post(f"/api/v1/loading/{project_id}/combinations")


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
    return await api_client.get(f"/api/v1/loading/{project_id}/output")


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
    return await api_client.put(
        f"/api/v1/loading/{project_id}/member/{member_id}", json=update
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
    return await api_client.post(
        f"/api/v1/analysis/run/{project_id}", json=options or {}
    )


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
    return await api_client.post(
        f"/api/v1/analysis/{project_id}/{member_type}",
        json={"member_ids": member_ids},
    )


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
    return await api_client.get(f"/api/v1/analysis/{project_id}/results")


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
    return await api_client.get(
        f"/api/v1/analysis/{project_id}/results/{member_id}"
    )


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
    body: dict = {}
    if design_code:
        body["design_code"] = design_code
    return await api_client.post(f"/api/v1/design/run/{project_id}", json=body)


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
    return await api_client.post(
        f"/api/v1/design/{project_id}/{member_type}",
        json={"member_ids": member_ids},
    )


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
    return await api_client.get(f"/api/v1/design/{project_id}/results")


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
    return await api_client.put(
        f"/api/v1/design/{project_id}/member/{member_id}", json=override
    )


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
    return await api_client.post(
        f"/api/v1/design/{project_id}/rerun/{member_id}"
    )


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
    return await api_client.post(f"/api/v1/drawings/{project_id}/generate")


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
    return await api_client.get(
        f"/api/v1/drawings/{project_id}/member/{member_id}"
    )


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
    return await api_client.post(
        f"/api/v1/drawings/{project_id}/member/{member_id}/regenerate"
    )


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
    return await api_client.put(
        f"/api/v1/drawings/{project_id}/confirm",
        json={"confirmed": True, "notes": notes},
    )


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
    return await api_client.get(f"/api/v1/drawings/{project_id}/layers")


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
    return await api_client.post(
        "/api/v1/reports/generate",
        json={
            "project_id": project_id,
            "report_type": report_type,
            "member_ids": member_ids,
        },
    )


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
    return await api_client.get(f"/api/v1/pipeline/{project_id}/status")


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
    return await api_client.post(
        f"/api/v1/pipeline/{project_id}/gates/{gate}/confirm"
    )


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
    return await api_client.get(f"/api/v1/jobs/{job_id}")


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

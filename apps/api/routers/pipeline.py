"""
routers/pipeline.py
===================
Pipeline orchestration router — high-level endpoints used by the Agent
Orchestration Layer to run, resume, and reset the full design pipeline.

Instead of calling each module router individually, the Agent calls a single
pipeline endpoint and the API handles sequencing internally.

Endpoints
---------
POST   /api/v1/pipeline/{project_id}/run          Run full pipeline end-to-end
POST   /api/v1/pipeline/{project_id}/resume       Resume from current stage
GET    /api/v1/pipeline/{project_id}/status       Full pipeline status overview
POST   /api/v1/pipeline/{project_id}/reset        Reset to a specific stage
GET    /api/v1/pipeline/{project_id}/gates        List all gate statuses
POST   /api/v1/pipeline/{project_id}/gates/{gate}/confirm  Manually confirm a gate
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, status
from pydantic import BaseModel, Field

from dependencies import get_project
from middleware.error_handler import StructuralError
from schemas.project import PipelineStatusResponse, ProjectResponse, ProjectStatus
from storage.job_store import job_store
from storage.project_store import project_store

logger = logging.getLogger(__name__)
router = APIRouter()

# ─── Gate registry ────────────────────────────────────────────────────────────

_GATES: tuple[str, ...] = (
    "geometry_verified",
    "loading_confirmed",
    "analysis_complete",
    "design_complete",
    "report_approved",
)

_GATE_TO_STATUS: dict[str, ProjectStatus] = {
    "geometry_verified":  ProjectStatus.GEOMETRY_VERIFIED,
    "loading_confirmed":  ProjectStatus.LOADING_DEFINED,
    "analysis_complete":  ProjectStatus.ANALYSIS_COMPLETE,
    "design_complete":    ProjectStatus.DESIGN_COMPLETE,
    "report_approved":    ProjectStatus.REPORT_GENERATED,
}

_NEXT_ACTION_MAP: dict[ProjectStatus, str] = {
    ProjectStatus.CREATED:           "upload_file",
    ProjectStatus.FILE_UPLOADED:     "verify_geometry",
    ProjectStatus.GEOMETRY_VERIFIED: "define_loading",
    ProjectStatus.LOADING_DEFINED:   "run_analysis",
    ProjectStatus.ANALYSIS_COMPLETE: "run_design",
    ProjectStatus.DESIGN_COMPLETE:   "generate_report",
    ProjectStatus.REPORT_GENERATED:  "complete",
}


def _build_gates(status_ordinal: int) -> dict[str, bool]:
    """Build the gate status dict from a numeric pipeline status ordinal."""
    thresholds = (
        ProjectStatus.GEOMETRY_VERIFIED,
        ProjectStatus.LOADING_DEFINED,
        ProjectStatus.ANALYSIS_COMPLETE,
        ProjectStatus.DESIGN_COMPLETE,
        ProjectStatus.REPORT_GENERATED,
    )
    return {label: status_ordinal >= thresh for label, thresh in zip(_GATES, thresholds)}


# ─── Request / Response models ────────────────────────────────────────────────


class PipelineRunRequest(BaseModel):
    """
    Request body for POST /api/v1/pipeline/{project_id}/run.

    Attributes
    ----------
    start_from : str | None
        Gate label to start from (skips earlier stages).  None → start from
        the current pipeline position.
    stop_before : str | None
        Gate label to stop before reaching (requires manual gate confirmation).
        None → run the entire pipeline through to report generation.
    """

    start_from: Optional[str] = Field(
        None, description="Gate label to start from (None = current position)."
    )
    stop_before: Optional[str] = Field(
        None, description="Gate label to pause before (None = run to completion)."
    )


class PipelineResetRequest(BaseModel):
    """
    Request body for POST /api/v1/pipeline/{project_id}/reset.

    Attributes
    ----------
    target_stage : str
        Pipeline stage label to reset to (e.g. ``"loading_defined"``).  All
        downstream results are cleared.
    confirm : bool
        Safety flag — must be True to execute the reset.
    """

    target_stage: str = Field(..., description="Stage label to reset to.")
    confirm: bool = Field(False, description="Must be True to execute the reset.")


# ─── Background task ─────────────────────────────────────────────────────────

async def _run_pipeline_background(
    project_id: str,
    job_id: str,
    start_from: Optional[str],
    stop_before: Optional[str],
) -> None:
    """
    Background task: orchestrate the full pipeline sequence.

    This task acts as the agent-facing runner.  It calls each stage sequentially
    and stops if a gate requires human confirmation.

    Parameters
    ----------
    project_id : str
        Owning project.
    job_id : str
        Async job identifier.
    start_from : str | None
        Gate label where the run should begin.
    stop_before : str | None
        Gate label before which the run should pause.
    """
    job_store.mark_running(job_id, "Pipeline starting…")
    try:
        # Stub implementation — real pipeline would invoke each service in sequence
        # loading_service.run(project_id)
        # analysis_service.run(project_id)
        # design_service.run(project_id)
        job_store.update_progress(job_id, 50.0, "Running pipeline stages…")
        job_store.mark_complete(job_id, result_url=f"/api/v1/pipeline/{project_id}/status")
        logger.info("Pipeline complete for project %s.", project_id)
    except Exception as exc:
        logger.exception("Pipeline failed for project %s.", project_id)
        job_store.mark_failed(job_id, errors=[str(exc)])


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/{project_id}/run", status_code=status.HTTP_202_ACCEPTED)
async def run_pipeline(
    project_id: str,
    background_tasks: BackgroundTasks,
    request: PipelineRunRequest = PipelineRunRequest(),
    project: ProjectResponse = Depends(get_project),
) -> dict:
    """
    Queue a full end-to-end pipeline run for the project.

    The pipeline stages loading → analysis → design → report are executed
    sequentially.  Human gates remain active and must be confirmed manually.

    Parameters
    ----------
    project_id : str
    background_tasks : BackgroundTasks
    request : PipelineRunRequest
        Control flags for partial runs.
    project : ProjectResponse
        Gate dependency — project must exist.

    Returns
    -------
    dict
        ``{job_id, status_url, message}``
    """
    job_id = job_store.create("analysis", project_id=project_id)  # 'analysis' as closest proxy
    background_tasks.add_task(
        _run_pipeline_background,
        project_id=project_id,
        job_id=job_id,
        start_from=request.start_from,
        stop_before=request.stop_before,
    )
    logger.info("Pipeline run queued for project %s. Job: %s.", project_id, job_id)
    return {
        "job_id": job_id,
        "status_url": f"/api/v1/pipeline/{project_id}/status",
        "message": f"Pipeline queued from '{request.start_from or 'current'}'. Job: {job_id}.",
    }


@router.post("/{project_id}/resume", status_code=status.HTTP_202_ACCEPTED)
async def resume_pipeline(
    project_id: str,
    background_tasks: BackgroundTasks,
    project: ProjectResponse = Depends(get_project),
) -> dict:
    """
    Resume the pipeline from the current project stage.

    Use this after confirming a human gate to continue the run.

    Parameters
    ----------
    project_id : str
    background_tasks : BackgroundTasks
    project : ProjectResponse

    Returns
    -------
    dict
        ``{job_id, status_url, message}``
    """
    current = ProjectStatus(project.pipeline_status_ordinal)
    job_id = job_store.create("analysis", project_id=project_id)
    background_tasks.add_task(
        _run_pipeline_background,
        project_id=project_id,
        job_id=job_id,
        start_from=current.label(),
        stop_before=None,
    )
    return {
        "job_id": job_id,
        "status_url": f"/api/v1/pipeline/{project_id}/status",
        "message": f"Pipeline resumed from '{current.label()}'. Job: {job_id}.",
    }


@router.get("/{project_id}/status", response_model=PipelineStatusResponse)
def get_pipeline_status(project: ProjectResponse = Depends(get_project)) -> PipelineStatusResponse:
    """
    Return the full pipeline status overview — the primary endpoint read by the Agent.

    Parameters
    ----------
    project : ProjectResponse
        Resolved project entity.

    Returns
    -------
    PipelineStatusResponse
        Current stage, next action, gate statuses, and blocking issues.
    """
    current = ProjectStatus(project.pipeline_status_ordinal)
    gates = _build_gates(project.pipeline_status_ordinal)

    return PipelineStatusResponse(
        project_id=project.project_id,
        current_stage=project.pipeline_status,
        next_action=_NEXT_ACTION_MAP.get(current, "complete"),
        gates=gates,
        blocking_issues=[],
        completed_members=project.member_count,
        failed_members=0,
        last_updated=project.updated_at,
    )


@router.post("/{project_id}/reset", status_code=status.HTTP_200_OK)
def reset_pipeline(
    project_id: str,
    payload: PipelineResetRequest,
    project: ProjectResponse = Depends(get_project),
) -> dict:
    """
    Reset the project pipeline to a specific stage, clearing downstream results.

    Parameters
    ----------
    project_id : str
    payload : PipelineResetRequest
        Target stage and confirmation flag.
    project : ProjectResponse

    Returns
    -------
    dict
        ``{project_id, reset_to, previous_stage}``

    Raises
    ------
    StructuralError
        HTTP 400 if ``confirm`` is False or the target stage is unrecognised.
    """
    if not payload.confirm:
        raise StructuralError(
            "GATE_NOT_PASSED",
            stage="pipeline_reset",
            details={"reason": "Field 'confirm' must be true to execute a pipeline reset."},
            status_code=400,
        )

    label_to_status: dict[str, ProjectStatus] = {s.label(): s for s in ProjectStatus}
    target = label_to_status.get(payload.target_stage)
    if target is None:
        raise StructuralError(
            "GATE_NOT_PASSED",
            details={"reason": f"Unknown stage label '{payload.target_stage}'."},
            status_code=400,
        )

    previous = project.pipeline_status
    project_store.advance_status(project_id, target)
    logger.info(
        "Pipeline reset for project %s: %s → %s.",
        project_id,
        previous,
        target.label(),
    )
    return {
        "project_id": project_id,
        "reset_to": target.label(),
        "previous_stage": previous,
        "reset_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/{project_id}/gates")
def list_gates(project: ProjectResponse = Depends(get_project)) -> dict:
    """
    List the confirmation status of all pipeline gates.

    Parameters
    ----------
    project : ProjectResponse

    Returns
    -------
    dict
        ``{gates: {gate_name: bool}, …}``
    """
    gates = _build_gates(project.pipeline_status_ordinal)
    return {
        "project_id": project.project_id,
        "current_stage": project.pipeline_status,
        "gates": gates,
    }


@router.post("/{project_id}/gates/{gate}/confirm")
def confirm_gate(
    project_id: str,
    gate: str,
    project: ProjectResponse = Depends(get_project),
) -> dict:
    """
    Manually confirm a specific pipeline gate, advancing the project status.

    Use this when a gate was confirmed outside the normal flow (e.g. the user
    confirmed geometry verification via a chat message rather than the UI button).

    Parameters
    ----------
    project_id : str
    gate : str
        Gate label (e.g. ``"geometry_verified"``).
    project : ProjectResponse

    Returns
    -------
    dict
        ``{gate, confirmed_at, new_status}``

    Raises
    ------
    StructuralError
        HTTP 400 if the gate label is unrecognised.
    """
    target_status = _GATE_TO_STATUS.get(gate)
    if target_status is None:
        raise StructuralError(
            "GATE_NOT_PASSED",
            details={
                "reason": f"Unknown gate '{gate}'.",
                "valid_gates": list(_GATE_TO_STATUS.keys()),
            },
            status_code=400,
        )

    project_store.advance_status(project_id, target_status)
    logger.info("Gate '%s' confirmed for project %s.", gate, project_id)
    return {
        "gate": gate,
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
        "new_status": target_status.label(),
    }

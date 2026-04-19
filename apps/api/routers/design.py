"""
routers/design.py
=================
Design Suite router — accepts analysis results and returns designed member
properties including reinforcement schedules.

Endpoints
---------
POST   /api/v1/design/{project_id}/run            Run full design (all members)
POST   /api/v1/design/{project_id}/beam           Design specific beam(s)
POST   /api/v1/design/{project_id}/slab           Design specific slab(s)
POST   /api/v1/design/{project_id}/column         Design specific column(s)
POST   /api/v1/design/{project_id}/wall           Design specific wall(s)
POST   /api/v1/design/{project_id}/footing        Design specific footing(s)
POST   /api/v1/design/{project_id}/staircase      Design specific staircase(s)
GET    /api/v1/design/{project_id}/results        Get all design results
PUT    /api/v1/design/{project_id}/member/{id}    Override a design parameter
POST   /api/v1/design/{project_id}/rerun/{id}     Rerun design for one member
GET    /api/v1/design/{project_id}/status/{job_id} Poll async design job

Gate enforcement
----------------
All endpoints require ``ANALYSIS_COMPLETE`` status.

IDE integration
---------------
``PUT /member/{member_id}`` is the primary endpoint called when an engineer
makes a geometry change in the chat panel (e.g. "change beam B1 to 300×600").
It re-checks limit states and flags if re-analysis is needed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, status

from dependencies import require_analysis_complete
from middleware.error_handler import StructuralError
from schemas.design import (
    DesignJobStarted,
    DesignResultsResponse,
    DesignRunRequest,
    MemberDesignOverride,
    MemberDesignOverrideResponse,
)
from schemas.project import ProjectResponse, ProjectStatus
from storage.job_store import job_store
from storage.project_store import project_store

logger = logging.getLogger(__name__)
router = APIRouter()

# In-process design results store (replace with DB in production)
_design_store: dict[str, dict[str, Any]] = {}

# Self-weight re-analysis threshold
_SELF_WEIGHT_THRESHOLD_PCT = 5.0


# ─── Background task ─────────────────────────────────────────────────────────

async def _run_design_background(
    project_id: str,
    job_id: str,
    member_ids: Optional[list[str]],
    design_code: Optional[str],
) -> None:
    """
    Background task: run the Design Suite for all (or a subset of) members.

    Parameters
    ----------
    project_id : str
        Owning project.
    job_id : str
        Async job identifier.
    member_ids : list[str] | None
        Members to design.  None → all registered members.
    design_code : str | None
        Code override for this run (BS8110 or EC2).
    """
    job_store.mark_running(job_id, "Initialising design suite…")
    errors: list[str] = []

    try:
        all_ids = member_ids or project_store.get_member_ids(project_id)
        total = max(len(all_ids), 1)

        # Stub: replace with actual Design Suite calls, e.g.:
        # from core.design.rc.bs8110.beam import BeamDesigner
        # ...

        results: list[dict[str, Any]] = []
        for i, mid in enumerate(all_ids, start=1):
            pct = (i / total) * 100
            job_store.update_progress(job_id, pct, f"Designing member {mid} ({i}/{total})…")

            # Placeholder
            results.append({
                "member_id": mid,
                "design_code": design_code or "BS8110",
                "status": "designed_stub",
                "reinforcement": {},
            })

        _design_store[project_id] = {
            "design_id": f"DES-{job_id}",
            "design_code": design_code or "BS8110",
            "members": results,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        project_store.advance_status(project_id, ProjectStatus.DESIGN_COMPLETE)
        job_store.mark_complete(job_id, result_url=f"/api/v1/design/{project_id}/results")
        logger.info("Design complete for project %s.", project_id)

    except Exception as exc:
        logger.exception("Design failed for project %s.", project_id)
        errors.append(str(exc))
        job_store.mark_failed(job_id, errors)


# ─── Shared helper ────────────────────────────────────────────────────────────

def _enqueue_design(
    project_id: str,
    background_tasks: BackgroundTasks,
    request: DesignRunRequest,
) -> DesignJobStarted:
    """
    Create a design job and register the background task.

    Parameters
    ----------
    project_id : str
    background_tasks : BackgroundTasks
    request : DesignRunRequest

    Returns
    -------
    DesignJobStarted
    """
    job_id = job_store.create("design", project_id=project_id)
    background_tasks.add_task(
        _run_design_background,
        project_id=project_id,
        job_id=job_id,
        member_ids=request.member_ids,
        design_code=request.design_code,
    )
    return DesignJobStarted(
        job_id=job_id,
        status_url=f"/api/v1/design/{project_id}/status/{job_id}",
        message=f"Design queued. Poll status_url for updates. Job: {job_id}.",
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/run/{project_id}", response_model=DesignJobStarted, status_code=status.HTTP_202_ACCEPTED)
async def run_full_design(
    project_id: str,
    background_tasks: BackgroundTasks,
    request: DesignRunRequest = DesignRunRequest(),
    project: ProjectResponse = Depends(require_analysis_complete),
) -> DesignJobStarted:
    """
    Queue a full design run for all members in the project.

    Returns immediately with a job ID.  When complete the project advances to
    ``DESIGN_COMPLETE``.

    Parameters
    ----------
    project_id : str
    background_tasks : BackgroundTasks
    request : DesignRunRequest
    project : ProjectResponse
        Gate dependency — ``ANALYSIS_COMPLETE`` required.

    Returns
    -------
    DesignJobStarted
    """
    logger.info("Full design queued for project %s.", project_id)
    return _enqueue_design(project_id, background_tasks, request)


@router.post("/{project_id}/beam", response_model=DesignJobStarted, status_code=status.HTTP_202_ACCEPTED)
async def design_beams(
    project_id: str,
    request: DesignRunRequest,
    background_tasks: BackgroundTasks,
    project: ProjectResponse = Depends(require_analysis_complete),
) -> DesignJobStarted:
    """
    Queue design for a specific set of beam members.

    Parameters
    ----------
    project_id : str
    request : DesignRunRequest
    background_tasks : BackgroundTasks
    project : ProjectResponse

    Returns
    -------
    DesignJobStarted
    """
    return _enqueue_design(project_id, background_tasks, request)


@router.post("/{project_id}/slab", response_model=DesignJobStarted, status_code=status.HTTP_202_ACCEPTED)
async def design_slabs(
    project_id: str,
    request: DesignRunRequest,
    background_tasks: BackgroundTasks,
    project: ProjectResponse = Depends(require_analysis_complete),
) -> DesignJobStarted:
    """
    Queue design for a specific set of slab members.

    Parameters
    ----------
    project_id : str
    request : DesignRunRequest
    background_tasks : BackgroundTasks
    project : ProjectResponse

    Returns
    -------
    DesignJobStarted
    """
    return _enqueue_design(project_id, background_tasks, request)


@router.post("/{project_id}/column", response_model=DesignJobStarted, status_code=status.HTTP_202_ACCEPTED)
async def design_columns(
    project_id: str,
    request: DesignRunRequest,
    background_tasks: BackgroundTasks,
    project: ProjectResponse = Depends(require_analysis_complete),
) -> DesignJobStarted:
    """
    Queue design for a specific set of column members.

    Parameters
    ----------
    project_id : str
    request : DesignRunRequest
    background_tasks : BackgroundTasks
    project : ProjectResponse

    Returns
    -------
    DesignJobStarted
    """
    return _enqueue_design(project_id, background_tasks, request)


@router.post("/{project_id}/wall", response_model=DesignJobStarted, status_code=status.HTTP_202_ACCEPTED)
async def design_walls(
    project_id: str,
    request: DesignRunRequest,
    background_tasks: BackgroundTasks,
    project: ProjectResponse = Depends(require_analysis_complete),
) -> DesignJobStarted:
    """
    Queue design for a specific set of wall members.

    Parameters
    ----------
    project_id : str
    request : DesignRunRequest
    background_tasks : BackgroundTasks
    project : ProjectResponse

    Returns
    -------
    DesignJobStarted
    """
    return _enqueue_design(project_id, background_tasks, request)


@router.post("/{project_id}/footing", response_model=DesignJobStarted, status_code=status.HTTP_202_ACCEPTED)
async def design_footings(
    project_id: str,
    request: DesignRunRequest,
    background_tasks: BackgroundTasks,
    project: ProjectResponse = Depends(require_analysis_complete),
) -> DesignJobStarted:
    """
    Queue design for a specific set of footing members.

    Parameters
    ----------
    project_id : str
    request : DesignRunRequest
    background_tasks : BackgroundTasks
    project : ProjectResponse

    Returns
    -------
    DesignJobStarted
    """
    return _enqueue_design(project_id, background_tasks, request)


@router.post("/{project_id}/staircase", response_model=DesignJobStarted, status_code=status.HTTP_202_ACCEPTED)
async def design_staircases(
    project_id: str,
    request: DesignRunRequest,
    background_tasks: BackgroundTasks,
    project: ProjectResponse = Depends(require_analysis_complete),
) -> DesignJobStarted:
    """
    Queue design for a specific set of staircase members.

    Parameters
    ----------
    project_id : str
    request : DesignRunRequest
    background_tasks : BackgroundTasks
    project : ProjectResponse

    Returns
    -------
    DesignJobStarted
    """
    return _enqueue_design(project_id, background_tasks, request)


@router.get("/{project_id}/status/{job_id}")
def get_design_status(
    project_id: str,
    job_id: str,
    project: ProjectResponse = Depends(require_analysis_complete),
) -> dict:
    """
    Poll the status of an async design job.

    Parameters
    ----------
    project_id : str
    job_id : str
    project : ProjectResponse

    Returns
    -------
    dict
        Full JobStatus dict.
    """
    return job_store.get_or_404(job_id).model_dump()


@router.get("/{project_id}/results", response_model=DesignResultsResponse)
def get_design_results(
    project_id: str,
    project: ProjectResponse = Depends(require_analysis_complete),
) -> DesignResultsResponse:
    """
    Return all completed design results for a project.

    Parameters
    ----------
    project_id : str
    project : ProjectResponse

    Returns
    -------
    DesignResultsResponse

    Raises
    ------
    StructuralError
        HTTP 404 if design has not been run yet.
    """
    result = _design_store.get(project_id)
    if result is None:
        raise StructuralError(
            "DESIGN_FAILED",
            stage="design",
            details={"reason": "No design results found. Run POST /run first."},
            status_code=404,
        )
    return DesignResultsResponse(
        project_id=project_id,
        design_id=result["design_id"],
        design_code=result["design_code"],
        member_count=len(result["members"]),
        members=result["members"],
        generated_at=result["generated_at"],
    )


@router.put("/{project_id}/member/{member_id}", response_model=MemberDesignOverrideResponse)
async def override_member_design(
    project_id: str,
    member_id: str,
    override: MemberDesignOverride,
    project: ProjectResponse = Depends(require_analysis_complete),
) -> MemberDesignOverrideResponse:
    """
    Apply a direct geometry or parameter override to a designed member.

    This is the **primary IDE interaction endpoint**.  When an engineer types
    "change beam B1 to 300×600" in the chat panel, the agent calls this endpoint.

    After applying the override, all limit states are re-checked.  If the
    self-weight changes by more than 5%, a warning is returned with a
    re-analysis URL.

    Parameters
    ----------
    project_id : str
    member_id : str
        Target member identifier.
    override : MemberDesignOverride
        Fields to update (only non-None values are applied).
    project : ProjectResponse
        Gate dependency.

    Returns
    -------
    MemberDesignOverrideResponse
        Updated result, optional warning, optional re-analysis URL.

    Raises
    ------
    StructuralError
        ``MEMBER_NOT_FOUND`` if the member is not in the design store.
    """
    store = _design_store.get(project_id)
    if store is None:
        raise StructuralError("DESIGN_FAILED", stage="design", status_code=404)

    member = next((m for m in store["members"] if m["member_id"] == member_id), None)
    if member is None:
        raise StructuralError("MEMBER_NOT_FOUND", member_id=member_id, status_code=404)

    # Apply override fields
    if override.b_mm is not None:
        member["b_mm"] = override.b_mm
    if override.h_mm is not None:
        member["h_mm"] = override.h_mm
    if override.cover_mm is not None:
        member["cover_mm"] = override.cover_mm
    if override.fck_MPa is not None:
        member["fck_MPa"] = override.fck_MPa
    if override.fcu_MPa is not None:
        member["fcu_MPa"] = override.fcu_MPa
    if override.fy_MPa is not None:
        member["fy_MPa"] = override.fy_MPa
    member.update(override.meta_updates)
    member["override_reason"] = override.reason
    member["override_at"] = datetime.now(timezone.utc).isoformat()

    # Stub: replace with actual re-check call
    # result = await design_service.recheck_member(project_id, member_id)
    self_weight_change_pct = 0.0  # placeholder

    warning = None
    reanalysis_url = None
    if self_weight_change_pct > _SELF_WEIGHT_THRESHOLD_PCT:
        warning = (
            f"Self-weight changed by {self_weight_change_pct:.1f}% "
            f"(threshold: {_SELF_WEIGHT_THRESHOLD_PCT}%). Re-analysis recommended."
        )
        reanalysis_url = f"/api/v1/analysis/{project_id}/run"

    logger.info(
        "Design override applied to %s in project %s. Reason: %s",
        member_id,
        project_id,
        override.reason or "(none)",
    )
    return MemberDesignOverrideResponse(
        result=member, warning=warning, reanalysis_url=reanalysis_url
    )


@router.post("/{project_id}/rerun/{member_id}", status_code=status.HTTP_202_ACCEPTED)
async def rerun_member_design(
    project_id: str,
    member_id: str,
    background_tasks: BackgroundTasks,
    project: ProjectResponse = Depends(require_analysis_complete),
) -> DesignJobStarted:
    """
    Rerun the design for a single member after a geometry override.

    Parameters
    ----------
    project_id : str
    member_id : str
    background_tasks : BackgroundTasks
    project : ProjectResponse

    Returns
    -------
    DesignJobStarted
    """
    request = DesignRunRequest(member_ids=[member_id])
    return _enqueue_design(project_id, background_tasks, request)

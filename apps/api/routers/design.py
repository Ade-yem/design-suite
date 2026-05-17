"""
routers/design.py
=================
Design Suite router — thin HTTP wrapper around ``services.design``.

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
from typing import Any, Optional

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
from schemas.project import ProjectResponse
from services.design import design_service
from storage.job_store import job_store

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Background task ─────────────────────────────────────────────────────────

async def _run_design_background(
    project_id: str,
    job_id: str,
    member_ids: Optional[list[str]],
    design_code: Optional[str],
) -> None:
    """
    Background task: call ``design_service.run()`` and update the job store.

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
    try:
        def _progress(step: str, pct: float) -> None:
            job_store.update_progress(job_id, pct, step)

        await design_service.run(
            project_id,
            member_ids=member_ids,
            design_code=design_code,
            progress_cb=_progress,
        )
        job_store.mark_complete(job_id, result_url=f"/api/v1/design/{project_id}/results")
        logger.info("Design complete for project %s.", project_id)
    except Exception as exc:
        logger.exception("Design failed for project %s.", project_id)
        job_store.mark_failed(job_id, errors=[str(exc)])



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
    try:
        result = design_service.get_results(project_id)
    except KeyError as exc:
        raise StructuralError(
            "DESIGN_FAILED",
            stage="design",
            details={"reason": str(exc)},
            status_code=404,
        ) from exc
    return DesignResultsResponse(
        project_id=project_id,
        design_id=result["design_id"],
        design_code=result["design_code"],
        member_count=result["member_count"],
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
    try:
        outcome = design_service.apply_override(
            project_id,
            member_id,
            override=override.model_dump(),
        )
    except KeyError as exc:
        raise StructuralError("MEMBER_NOT_FOUND", member_id=member_id, status_code=404) from exc

    reanalysis_url = (
        f"/api/v1/analysis/{project_id}/run" if outcome.get("reanalysis_needed") else None
    )
    return MemberDesignOverrideResponse(
        result=outcome["result"],
        warning=outcome.get("warning"),
        reanalysis_url=reanalysis_url,
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

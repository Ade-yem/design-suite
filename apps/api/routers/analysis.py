"""
routers/analysis.py
===================
Analysis Engine router — exposes the structural analysis engine via HTTP.

Endpoints
---------
POST   /api/v1/analysis/{project_id}/run          Run full analysis (all members)
POST   /api/v1/analysis/{project_id}/beam         Analyse specific beam(s)
POST   /api/v1/analysis/{project_id}/slab         Analyse specific slab(s)
POST   /api/v1/analysis/{project_id}/column       Analyse specific column(s)
POST   /api/v1/analysis/{project_id}/wall         Analyse specific wall(s)
POST   /api/v1/analysis/{project_id}/footing      Analyse specific footing(s)
POST   /api/v1/analysis/{project_id}/staircase    Analyse specific staircase(s)
GET    /api/v1/analysis/{project_id}/results      Get all analysis results
GET    /api/v1/analysis/{project_id}/results/{id} Get results for one member
DELETE /api/v1/analysis/{project_id}/results      Clear and re-run
GET    /api/v1/analysis/{project_id}/status/{job_id} Poll async job status

Gate enforcement
----------------
All endpoints require ``LOADING_DEFINED`` status.

Rule
----
This router never performs calculations — it delegates to ``services/analysis/``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, status

from dependencies import require_loading_defined
from middleware.error_handler import StructuralError
from schemas.analysis import (
    AnalysisJobStarted,
    AnalysisOptions,
    AnalysisResultsResponse,
    AnalysisStatusResponse,
    AnalysisProgress,
    SingleMemberAnalysisRequest,
)
from schemas.project import ProjectResponse, ProjectStatus
from storage.job_store import job_store
from storage.project_store import project_store

logger = logging.getLogger(__name__)
router = APIRouter()

# In-process results store (replace with DB in production)
_analysis_store: dict[str, dict[str, Any]] = {}


# ─── Background task ─────────────────────────────────────────────────────────

async def _run_analysis_background(
    project_id: str,
    job_id: str,
    member_ids: Optional[list[str]],
    options: AnalysisOptions,
) -> None:
    """
    Background task: run the Analysis Engine for all (or a subset of) members.

    Progress updates are pushed to the job store so the frontend can poll the
    status endpoint and display live output in the IDE chat panel.

    Parameters
    ----------
    project_id : str
        Owning project.
    job_id : str
        Async job identifier.
    member_ids : list[str] | None
        Members to analyse.  None → all registered members.
    options : AnalysisOptions
        Solver configuration.
    """
    job_store.mark_running(job_id, "Initialising analysis engine…")
    errors: list[str] = []

    try:
        all_ids = member_ids or project_store.get_member_ids(project_id)
        total = max(len(all_ids), 1)

        # Stub: replace with actual AnalysisEngine invocations, e.g.:
        # from core.analysis import AnalysisEngine
        # from storage.loading_store import get_loading_output
        # engine = AnalysisEngine(design_code=project.design_code)
        # ...

        results: list[dict[str, Any]] = []
        for i, mid in enumerate(all_ids, start=1):
            pct = (i / total) * 100
            job_store.update_progress(job_id, pct, f"Analysing member {mid} ({i}/{total})…")

            # Placeholder — real call would be:
            # result = engine.analyze_member(load_data, geometry_meta)
            results.append({"member_id": mid, "status": "analysed_stub"})

        _analysis_store[project_id] = {
            "analysis_id": f"ANA-{job_id}",
            "design_code": "BS8110",
            "members": results,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        project_store.advance_status(project_id, ProjectStatus.ANALYSIS_COMPLETE)
        job_store.mark_complete(job_id, result_url=f"/api/v1/analysis/{project_id}/results")
        logger.info("Analysis complete for project %s.", project_id)

    except Exception as exc:
        logger.exception("Analysis failed for project %s.", project_id)
        errors.append(str(exc))
        job_store.mark_failed(job_id, errors)


# ─── Shared helper ────────────────────────────────────────────────────────────

def _enqueue_analysis(
    project_id: str,
    background_tasks: BackgroundTasks,
    member_ids: Optional[list[str]],
    options: AnalysisOptions,
) -> AnalysisJobStarted:
    """
    Create a job entry, register the background task, and return the job reference.

    Parameters
    ----------
    project_id : str
        Owning project.
    background_tasks : BackgroundTasks
        FastAPI BG task queue.
    member_ids : list[str] | None
        Members to analyse (None = all).
    options : AnalysisOptions
        Solver options.

    Returns
    -------
    AnalysisJobStarted
    """
    job_id = job_store.create("analysis", project_id=project_id)
    background_tasks.add_task(
        _run_analysis_background,
        project_id=project_id,
        job_id=job_id,
        member_ids=member_ids,
        options=options,
    )
    return AnalysisJobStarted(
        job_id=job_id,
        status_url=f"/api/v1/analysis/{project_id}/status/{job_id}",
        message=f"Analysis queued. Poll status_url for updates. Job: {job_id}.",
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/run/{project_id}", response_model=AnalysisJobStarted, status_code=status.HTTP_202_ACCEPTED)
async def run_full_analysis(
    project_id: str,
    background_tasks: BackgroundTasks,
    options: AnalysisOptions = AnalysisOptions(),
    project: ProjectResponse = Depends(require_loading_defined),
) -> AnalysisJobStarted:
    """
    Queue a full structural analysis run for all members in the project.

    Returns immediately with a job ID.  Poll ``status_url`` for progress.
    When complete, the project advances to ``ANALYSIS_COMPLETE``.

    Parameters
    ----------
    project_id : str
        Target project.
    background_tasks : BackgroundTasks
        FastAPI background task queue.
    options : AnalysisOptions
        Solver configuration (pattern loading, iteration, etc.).
    project : ProjectResponse
        Gate dependency — ``LOADING_DEFINED`` required.

    Returns
    -------
    AnalysisJobStarted
    """
    logger.info("Full analysis queued for project %s.", project_id)
    return _enqueue_analysis(project_id, background_tasks, options.member_ids, options)


@router.post("/{project_id}/beam", response_model=AnalysisJobStarted, status_code=status.HTTP_202_ACCEPTED)
async def analyse_beams(
    project_id: str,
    payload: SingleMemberAnalysisRequest,
    background_tasks: BackgroundTasks,
    project: ProjectResponse = Depends(require_loading_defined),
) -> AnalysisJobStarted:
    """
    Queue analysis for a specific set of beam members.

    Parameters
    ----------
    project_id : str
        Target project.
    payload : SingleMemberAnalysisRequest
        List of beam member IDs and solver options.
    background_tasks : BackgroundTasks
    project : ProjectResponse
        Gate dependency.

    Returns
    -------
    AnalysisJobStarted
    """
    return _enqueue_analysis(project_id, background_tasks, payload.member_ids, payload.options)


@router.post("/{project_id}/slab", response_model=AnalysisJobStarted, status_code=status.HTTP_202_ACCEPTED)
async def analyse_slabs(
    project_id: str,
    payload: SingleMemberAnalysisRequest,
    background_tasks: BackgroundTasks,
    project: ProjectResponse = Depends(require_loading_defined),
) -> AnalysisJobStarted:
    """
    Queue analysis for a specific set of slab members.

    Parameters
    ----------
    project_id : str
    payload : SingleMemberAnalysisRequest
    background_tasks : BackgroundTasks
    project : ProjectResponse

    Returns
    -------
    AnalysisJobStarted
    """
    return _enqueue_analysis(project_id, background_tasks, payload.member_ids, payload.options)


@router.post("/{project_id}/column", response_model=AnalysisJobStarted, status_code=status.HTTP_202_ACCEPTED)
async def analyse_columns(
    project_id: str,
    payload: SingleMemberAnalysisRequest,
    background_tasks: BackgroundTasks,
    project: ProjectResponse = Depends(require_loading_defined),
) -> AnalysisJobStarted:
    """
    Queue analysis for a specific set of column members.

    Parameters
    ----------
    project_id : str
    payload : SingleMemberAnalysisRequest
    background_tasks : BackgroundTasks
    project : ProjectResponse

    Returns
    -------
    AnalysisJobStarted
    """
    return _enqueue_analysis(project_id, background_tasks, payload.member_ids, payload.options)


@router.post("/{project_id}/wall", response_model=AnalysisJobStarted, status_code=status.HTTP_202_ACCEPTED)
async def analyse_walls(
    project_id: str,
    payload: SingleMemberAnalysisRequest,
    background_tasks: BackgroundTasks,
    project: ProjectResponse = Depends(require_loading_defined),
) -> AnalysisJobStarted:
    """
    Queue analysis for a specific set of wall members.

    Parameters
    ----------
    project_id : str
    payload : SingleMemberAnalysisRequest
    background_tasks : BackgroundTasks
    project : ProjectResponse

    Returns
    -------
    AnalysisJobStarted
    """
    return _enqueue_analysis(project_id, background_tasks, payload.member_ids, payload.options)


@router.post("/{project_id}/footing", response_model=AnalysisJobStarted, status_code=status.HTTP_202_ACCEPTED)
async def analyse_footings(
    project_id: str,
    payload: SingleMemberAnalysisRequest,
    background_tasks: BackgroundTasks,
    project: ProjectResponse = Depends(require_loading_defined),
) -> AnalysisJobStarted:
    """
    Queue analysis for a specific set of footing members.

    Parameters
    ----------
    project_id : str
    payload : SingleMemberAnalysisRequest
    background_tasks : BackgroundTasks
    project : ProjectResponse

    Returns
    -------
    AnalysisJobStarted
    """
    return _enqueue_analysis(project_id, background_tasks, payload.member_ids, payload.options)


@router.post("/{project_id}/staircase", response_model=AnalysisJobStarted, status_code=status.HTTP_202_ACCEPTED)
async def analyse_staircases(
    project_id: str,
    payload: SingleMemberAnalysisRequest,
    background_tasks: BackgroundTasks,
    project: ProjectResponse = Depends(require_loading_defined),
) -> AnalysisJobStarted:
    """
    Queue analysis for a specific set of staircase members.

    Parameters
    ----------
    project_id : str
    payload : SingleMemberAnalysisRequest
    background_tasks : BackgroundTasks
    project : ProjectResponse

    Returns
    -------
    AnalysisJobStarted
    """
    return _enqueue_analysis(project_id, background_tasks, payload.member_ids, payload.options)


@router.get("/{project_id}/status/{job_id}", response_model=AnalysisStatusResponse)
def get_analysis_status(
    project_id: str,
    job_id: str,
    project: ProjectResponse = Depends(require_loading_defined),
) -> AnalysisStatusResponse:
    """
    Poll the status of an async analysis job.

    This drives the **live status log in the IDE left chat panel**.

    Parameters
    ----------
    project_id : str
    job_id : str
        Job identifier returned by the run endpoint.
    project : ProjectResponse
        Gate dependency.

    Returns
    -------
    AnalysisStatusResponse
        Progress, status, and errors.
    """
    job = job_store.get_or_404(job_id)
    all_ids = project_store.get_member_ids(project_id)
    total = len(all_ids)
    completed = int(job.progress_pct / 100 * total) if total > 0 else 0

    return AnalysisStatusResponse(
        job_id=job_id,
        status=job.status,
        progress=AnalysisProgress(
            total_members=total,
            completed=completed,
            current_stage=job.current_step,
        ),
        errors=job.errors,
        result_url=job.result_url,
    )


@router.get("/{project_id}/results", response_model=AnalysisResultsResponse)
def get_analysis_results(
    project_id: str,
    project: ProjectResponse = Depends(require_loading_defined),
) -> AnalysisResultsResponse:
    """
    Return all completed analysis results for a project.

    Parameters
    ----------
    project_id : str
    project : ProjectResponse
        Gate dependency.

    Returns
    -------
    AnalysisResultsResponse

    Raises
    ------
    StructuralError
        HTTP 404 if analysis has not been run yet.
    """
    result = _analysis_store.get(project_id)
    if result is None:
        raise StructuralError(
            "ANALYSIS_FAILED",
            stage="analysis",
            details={"reason": "No analysis results found. Run POST /run first."},
            status_code=404,
        )
    return AnalysisResultsResponse(
        project_id=project_id,
        analysis_id=result["analysis_id"],
        design_code=result["design_code"],
        member_count=len(result["members"]),
        members=result["members"],
        generated_at=result["generated_at"],
    )


@router.get("/{project_id}/results/{member_id}")
def get_member_analysis_result(
    project_id: str,
    member_id: str,
    project: ProjectResponse = Depends(require_loading_defined),
) -> dict:
    """
    Return the analysis result for a single member.

    Parameters
    ----------
    project_id : str
    member_id : str
    project : ProjectResponse

    Returns
    -------
    dict
        Single-member analysis result.

    Raises
    ------
    StructuralError
        ``MEMBER_NOT_FOUND`` if no result exists for this member.
    """
    result = _analysis_store.get(project_id)
    if result is None:
        raise StructuralError("ANALYSIS_FAILED", stage="analysis", status_code=404)
    member_result = next(
        (m for m in result["members"] if m["member_id"] == member_id), None
    )
    if member_result is None:
        raise StructuralError("MEMBER_NOT_FOUND", member_id=member_id, status_code=404)
    return member_result


@router.delete("/{project_id}/results", status_code=status.HTTP_204_NO_CONTENT)
def clear_analysis_results(
    project_id: str,
    project: ProjectResponse = Depends(require_loading_defined),
) -> None:
    """
    Clear all analysis results for a project, resetting it for a fresh run.

    Parameters
    ----------
    project_id : str
    project : ProjectResponse
        Gate dependency.
    """
    _analysis_store.pop(project_id, None)
    logger.info("Analysis results cleared for project %s.", project_id)

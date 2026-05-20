"""
routers/jobs.py
===============
Async job management router — exposes job status polling and cancellation
for all long-running operations across the pipeline.

Endpoints
---------
GET    /api/v1/jobs/{job_id}          Poll a single job's status
DELETE /api/v1/jobs/{job_id}          Cancel a running job
GET    /api/v1/jobs/project/{id}      All jobs for a project

These endpoints are technology-agnostic — they work with the in-process
``job_store`` in development and will work with a Redis backend in production
by swapping the store implementation.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, status

from schemas.jobs import JobStatus
from storage.job_store import job_store

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str) -> JobStatus:
    """
    Return the current status, progress, and result URL for an async job.

    Parameters
    ----------
    job_id : str
        Job identifier returned by any long-running endpoint.

    Returns
    -------
    JobStatus
        Full status snapshot including progress, current step, and errors.

    Raises
    ------
    StructuralError
        HTTP 404 ``JOB_NOT_FOUND`` if the job ID does not exist.
    """
    return await job_store.get_or_404(job_id)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_job(job_id: str) -> None:
    """
    Cancel a queued or running job.

    Completed, failed, or already-cancelled jobs are not affected.

    Parameters
    ----------
    job_id : str
        Job identifier to cancel.

    Raises
    ------
    StructuralError
        HTTP 404 ``JOB_NOT_FOUND`` if the job ID does not exist.
    """
    await job_store.get_or_404(job_id)  # 404 check
    cancelled = await job_store.cancel(job_id)
    if cancelled:
        logger.info("Job %s cancelled.", job_id)


@router.get("/project/{project_id}", response_model=list[JobStatus])
async def list_project_jobs(project_id: str) -> list[JobStatus]:
    """
    Return all jobs associated with a project, sorted most-recent-first.

    Parameters
    ----------
    project_id : str
        Owning project identifier.

    Returns
    -------
    list[JobStatus]
        All jobs for the project.
    """
    return await job_store.list_for_project(project_id)

"""
routers/jobs.py
===============
Async job management router — exposes job status polling and cancellation
for all long-running operations across the pipeline.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status

from auth.dependencies import current_active_user
from db.models.user import User
from dependencies import get_project
from middleware.error_handler import StructuralError
from schemas.jobs import JobStatus
from schemas.project import ProjectResponse
from storage.job_store import job_store
from storage.project_store import project_store

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{job_id}", response_model=JobStatus)
async def get_job_status(
    job_id: str,
    user: User = Depends(current_active_user),
) -> JobStatus:
    """
    Return the current status, progress, and result URL for an async job.

    Parameters
    ----------
    job_id : str
        Job identifier returned by any long-running endpoint.
    user : User
        The authenticated current user.

    Returns
    -------
    JobStatus
        Full status snapshot including progress, current step, and errors.

    Raises
    ------
    StructuralError
        HTTP 404 JOB_NOT_FOUND if the job ID does not exist, or if the
        associated project does not belong to the user's organisation.
    """
    job = await job_store.get_or_404(job_id)
    # Enforce tenant check
    if not job.project_id:
        raise StructuralError(
            error_code="JOB_NOT_FOUND",
            details={"job_id": job_id, "reason": "Job has no associated project_id"},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    await project_store.get_or_404(job.project_id, organisation_id=user.organisation_id)
    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_job(
    job_id: str,
    user: User = Depends(current_active_user),
) -> None:
    """
    Cancel a queued or running job.

    Completed, failed, or already-cancelled jobs are not affected.

    Parameters
    ----------
    job_id : str
        Job identifier to cancel.
    user : User
        The authenticated current user.

    Raises
    ------
    StructuralError
        HTTP 404 JOB_NOT_FOUND if the job ID does not exist, or if the
        associated project does not belong to the user's organisation.
    """
    job = await job_store.get_or_404(job_id)  # 404 check
    # Enforce tenant check
    if not job.project_id:
        raise StructuralError(
            error_code="JOB_NOT_FOUND",
            details={"job_id": job_id, "reason": "Job has no associated project_id"},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    await project_store.get_or_404(job.project_id, organisation_id=user.organisation_id)

    cancelled = await job_store.cancel(job_id)
    if cancelled:
        logger.info("Job %s cancelled.", job_id)


@router.get("/project/{project_id}", response_model=list[JobStatus])
async def list_project_jobs(
    project_id: str,
    project: ProjectResponse = Depends(get_project),
) -> list[JobStatus]:
    """
    Return all jobs associated with a project, sorted most-recent-first.

    Parameters
    ----------
    project_id : str
        Owning project identifier.
    project : ProjectResponse
        Resolved and org-scoped project dependency.

    Returns
    -------
    list[JobStatus]
        All jobs for the project.
    """
    return await job_store.list_for_project(project_id)


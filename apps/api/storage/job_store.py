"""
storage/job_store.py
====================
In-memory async job queue and status store.

Long-running operations (file parsing, full analysis, design runs, report
generation) are submitted to this store and return a ``job_id`` immediately.
Callers poll ``GET /api/v1/jobs/{job_id}`` for progress and the result URL.

In production, replace ``_jobs`` with a Redis-backed Celery task store.

Public interface
----------------
JobStore.create(job_type, context)       → str  (job_id)
JobStore.get(job_id)                     → JobStatus | None
JobStore.get_or_404(job_id)              → JobStatus
JobStore.update_progress(job_id, pct, step) → None
JobStore.mark_running(job_id)            → None
JobStore.mark_complete(job_id, result_url) → None
JobStore.mark_failed(job_id, errors)     → None
JobStore.cancel(job_id)                  → bool
JobStore.list_for_project(project_id)    → list[JobStatus]
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import status as http_status

from middleware.error_handler import StructuralError
from schemas.jobs import JobStatus


class JobStore:
    """
    Thread-safe (single-process) in-memory job registry.

    Each job entry maps ``job_id → JobStatus``.  A separate index maps
    ``project_id → set[job_id]`` for efficient project-level queries.

    Attributes
    ----------
    _jobs : dict[str, JobStatus]
        Job registry.
    _project_index : dict[str, set[str]]
        Inverted index: project_id → set of job_ids.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, JobStatus] = {}
        self._project_index: dict[str, set[str]] = {}

    def create(
        self,
        job_type: Literal["parsing", "analysis", "design", "reporting"],
        project_id: Optional[str] = None,
    ) -> str:
        """
        Enqueue a new job and return its ID.

        Parameters
        ----------
        job_type : str
            Category: ``parsing | analysis | design | reporting``.
        project_id : str | None
            Owning project — used for ``list_for_project``.

        Returns
        -------
        str
            Unique job identifier (e.g. ``"JOB-a1b2c3d4"``).
        """
        job_id = f"JOB-{uuid.uuid4().hex[:8].upper()}"
        job = JobStatus(
            job_id=job_id,
            job_type=job_type,
            status="queued",
            progress_pct=0.0,
            current_step="Waiting in queue…",
        )
        self._jobs[job_id] = job
        if project_id:
            self._project_index.setdefault(project_id, set()).add(job_id)
        return job_id

    def get(self, job_id: str) -> Optional[JobStatus]:
        """
        Return a job status by ID.

        Parameters
        ----------
        job_id : str
            Job identifier.

        Returns
        -------
        JobStatus | None
        """
        return self._jobs.get(job_id)

    def get_or_404(self, job_id: str) -> JobStatus:
        """
        Return a job status or raise a 404 StructuralError.

        Parameters
        ----------
        job_id : str
            Job identifier.

        Returns
        -------
        JobStatus

        Raises
        ------
        StructuralError
            HTTP 404 if job_id not found.
        """
        job = self.get(job_id)
        if job is None:
            raise StructuralError(
                "JOB_NOT_FOUND",
                details={"job_id": job_id},
                status_code=http_status.HTTP_404_NOT_FOUND,
            )
        return job

    def mark_running(self, job_id: str, step: str = "Starting…") -> None:
        """
        Transition a job to ``running`` status and record start time.

        Parameters
        ----------
        job_id : str
            Job identifier.
        step : str
            Initial step description.
        """
        job = self._jobs.get(job_id)
        if job:
            self._jobs[job_id] = job.model_copy(
                update={
                    "status": "running",
                    "current_step": step,
                    "started_at": datetime.now(timezone.utc),
                }
            )

    def update_progress(self, job_id: str, pct: float, step: str) -> None:
        """
        Update the progress percentage and current step description.

        Parameters
        ----------
        job_id : str
            Job identifier.
        pct : float
            Completion percentage (0.0–100.0).
        step : str
            Human-readable description of the active step.
        """
        job = self._jobs.get(job_id)
        if job:
            self._jobs[job_id] = job.model_copy(
                update={"progress_pct": min(pct, 99.9), "current_step": step}
            )

    def mark_complete(self, job_id: str, result_url: Optional[str] = None) -> None:
        """
        Transition a job to ``complete`` status.

        Parameters
        ----------
        job_id : str
            Job identifier.
        result_url : str | None
            Relative URL the client should GET to retrieve the result.
        """
        job = self._jobs.get(job_id)
        if job:
            self._jobs[job_id] = job.model_copy(
                update={
                    "status": "complete",
                    "progress_pct": 100.0,
                    "current_step": "Complete.",
                    "completed_at": datetime.now(timezone.utc),
                    "result_url": result_url,
                }
            )

    def mark_failed(self, job_id: str, errors: list[str]) -> None:
        """
        Transition a job to ``failed`` status with error messages.

        Parameters
        ----------
        job_id : str
            Job identifier.
        errors : list[str]
            Error messages accumulated during the run.
        """
        job = self._jobs.get(job_id)
        if job:
            self._jobs[job_id] = job.model_copy(
                update={
                    "status": "failed",
                    "current_step": "Failed.",
                    "completed_at": datetime.now(timezone.utc),
                    "errors": errors,
                }
            )

    def cancel(self, job_id: str) -> bool:
        """
        Cancel a queued or running job.

        Parameters
        ----------
        job_id : str
            Job identifier.

        Returns
        -------
        bool
            True if cancelled, False if job not found or already terminal.
        """
        job = self._jobs.get(job_id)
        if job and job.status in ("queued", "running"):
            self._jobs[job_id] = job.model_copy(
                update={
                    "status": "cancelled",
                    "completed_at": datetime.now(timezone.utc),
                }
            )
            return True
        return False

    def list_for_project(self, project_id: str) -> list[JobStatus]:
        """
        Return all jobs associated with a given project.

        Parameters
        ----------
        project_id : str
            Owning project identifier.

        Returns
        -------
        list[JobStatus]
            Jobs sorted by started_at descending (most recent first).
        """
        job_ids = self._project_index.get(project_id, set())
        jobs = [self._jobs[jid] for jid in job_ids if jid in self._jobs]
        return sorted(jobs, key=lambda j: (j.started_at or datetime.min), reverse=True)


# ── Singleton ────────────────────────────────────────────────────────────────
job_store = JobStore()

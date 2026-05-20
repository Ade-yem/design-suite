"""
storage/job_store.py
====================
Pluggable async job queue and status store.

Supports two backends controlled by ``settings.JOB_STORE_BACKEND``:
- ``"memory"`` — in-process dict store (development / testing)
- ``"redis"``  — redis.asyncio store with TTL-based expiry

The public interface is identical for both backends (all methods are
``async def``) so routers and agents call ``await job_store.<method>()``
regardless of the active backend.

Long-running operations (file parsing, full analysis, design runs, report
generation) are submitted to this store and return a ``job_id`` immediately.
Callers poll ``GET /api/v1/jobs/{job_id}`` for progress and the result URL.

Public interface
----------------
create(job_type, project_id)             → str  (job_id)
get(job_id)                              → JobStatus | None
get_or_404(job_id)                       → JobStatus
mark_running(job_id, step)               → None
update_progress(job_id, pct, step)       → None
mark_complete(job_id, result_url)        → None
mark_failed(job_id, errors)              → None
cancel(job_id)                           → bool
list_for_project(project_id)             → list[JobStatus]
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import status as http_status

from middleware.error_handler import StructuralError
from schemas.jobs import JobStatus


# ── In-memory implementation ──────────────────────────────────────────────────


class MemoryJobStore:
    """
    In-process in-memory job registry.

    All methods are ``async def`` with synchronous bodies so they can be
    awaited uniformly by callers without importing asyncio.

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

    async def create(
        self,
        job_type: Literal["parsing", "analysis", "design", "reporting", "drawings"],
        project_id: Optional[str] = None,
    ) -> str:
        job_id = f"JOB-{uuid.uuid4().hex[:8].upper()}"
        job = JobStatus(
            job_id=job_id,
            job_type=job_type if job_type in ("parsing", "analysis", "design", "reporting", "drawings") else "analysis",
            status="queued",
            progress_pct=0.0,
            current_step="Waiting in queue…",
        )
        self._jobs[job_id] = job
        if project_id:
            self._project_index.setdefault(project_id, set()).add(job_id)
        return job_id

    async def get(self, job_id: str) -> Optional[JobStatus]:
        return self._jobs.get(job_id)

    async def get_or_404(self, job_id: str) -> JobStatus:
        job = self._jobs.get(job_id)
        if job is None:
            raise StructuralError(
                "JOB_NOT_FOUND",
                details={"job_id": job_id},
                status_code=http_status.HTTP_404_NOT_FOUND,
            )
        return job

    async def mark_running(self, job_id: str, step: str = "Starting…") -> None:
        job = self._jobs.get(job_id)
        if job:
            self._jobs[job_id] = job.model_copy(
                update={
                    "status": "running",
                    "current_step": step,
                    "started_at": datetime.now(timezone.utc),
                }
            )

    async def update_progress(self, job_id: str, pct: float, step: str) -> None:
        job = self._jobs.get(job_id)
        if job:
            self._jobs[job_id] = job.model_copy(
                update={"progress_pct": min(pct, 99.9), "current_step": step}
            )

    async def mark_complete(self, job_id: str, result_url: Optional[str] = None) -> None:
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

    async def mark_failed(self, job_id: str, errors: list[str]) -> None:
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

    async def cancel(self, job_id: str) -> bool:
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

    async def list_for_project(self, project_id: str) -> list[JobStatus]:
        job_ids = self._project_index.get(project_id, set())
        jobs = [self._jobs[jid] for jid in job_ids if jid in self._jobs]
        return sorted(jobs, key=lambda j: (j.started_at or datetime.min), reverse=True)


# ── Redis implementation ──────────────────────────────────────────────────────


class RedisJobStore:
    """
    Redis-backed job store using ``redis.asyncio``.

    Key patterns
    ------------
    - Job data  : ``structai:job:{job_id}``       (string, JSON, TTL)
    - Proj index: ``structai:proj_jobs:{project_id}`` (Set of job_ids, TTL)

    The connection is created lazily on first use.
    """

    _redis = None

    def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as aioredis
            from config import settings

            if not settings.REDIS_URL:
                raise RuntimeError(
                    "REDIS_URL is not set. "
                    "Set it in your .env file or use the in-memory job store backend."
                )
            self.__class__._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._redis

    def _job_key(self, job_id: str) -> str:
        return f"structai:job:{job_id}"

    def _proj_key(self, project_id: str) -> str:
        return f"structai:proj_jobs:{project_id}"

    async def create(
        self,
        job_type: Literal["parsing", "analysis", "design", "reporting", "drawings"],
        project_id: Optional[str] = None,
    ) -> str:
        from config import settings

        safe_type = job_type if job_type in ("parsing", "analysis", "design", "reporting", "drawings") else "analysis"
        job_id = f"JOB-{uuid.uuid4().hex[:8].upper()}"
        job = JobStatus(
            job_id=job_id,
            job_type=safe_type,
            status="queued",
            progress_pct=0.0,
            current_step="Waiting in queue…",
        )
        r = self._get_redis()
        ttl = settings.JOB_STORE_TTL_SECONDS
        await r.set(self._job_key(job_id), job.model_dump_json(), ex=ttl)
        if project_id:
            await r.sadd(self._proj_key(project_id), job_id)
            await r.expire(self._proj_key(project_id), ttl)
        return job_id

    async def get(self, job_id: str) -> Optional[JobStatus]:
        r = self._get_redis()
        raw = await r.get(self._job_key(job_id))
        if raw is None:
            return None
        return JobStatus.model_validate_json(raw)

    async def get_or_404(self, job_id: str) -> JobStatus:
        job = await self.get(job_id)
        if job is None:
            raise StructuralError(
                "JOB_NOT_FOUND",
                details={"job_id": job_id},
                status_code=http_status.HTTP_404_NOT_FOUND,
            )
        return job

    async def _update_job(self, job_id: str, updates: dict) -> None:
        """Fetch, patch, and re-store a job with the current TTL."""
        from config import settings

        r = self._get_redis()
        raw = await r.get(self._job_key(job_id))
        if raw is None:
            return
        job = JobStatus.model_validate_json(raw)
        updated = job.model_copy(update=updates)
        await r.set(
            self._job_key(job_id),
            updated.model_dump_json(),
            ex=settings.JOB_STORE_TTL_SECONDS,
        )

    async def mark_running(self, job_id: str, step: str = "Starting…") -> None:
        await self._update_job(
            job_id,
            {
                "status": "running",
                "current_step": step,
                "started_at": datetime.now(timezone.utc),
            },
        )

    async def update_progress(self, job_id: str, pct: float, step: str) -> None:
        await self._update_job(
            job_id,
            {"progress_pct": min(pct, 99.9), "current_step": step},
        )

    async def mark_complete(self, job_id: str, result_url: Optional[str] = None) -> None:
        await self._update_job(
            job_id,
            {
                "status": "complete",
                "progress_pct": 100.0,
                "current_step": "Complete.",
                "completed_at": datetime.now(timezone.utc),
                "result_url": result_url,
            },
        )

    async def mark_failed(self, job_id: str, errors: list[str]) -> None:
        await self._update_job(
            job_id,
            {
                "status": "failed",
                "current_step": "Failed.",
                "completed_at": datetime.now(timezone.utc),
                "errors": errors,
            },
        )

    async def cancel(self, job_id: str) -> bool:
        job = await self.get(job_id)
        if job is None:
            return False
        if job.status not in ("queued", "running"):
            return False
        await self._update_job(
            job_id,
            {
                "status": "cancelled",
                "completed_at": datetime.now(timezone.utc),
            },
        )
        return True

    async def list_for_project(self, project_id: str) -> list[JobStatus]:
        r = self._get_redis()
        job_ids = await r.smembers(self._proj_key(project_id))
        if not job_ids:
            return []
        keys = [self._job_key(jid) for jid in job_ids]
        raws = await r.mget(*keys)
        jobs = []
        for raw in raws:
            if raw is not None:
                jobs.append(JobStatus.model_validate_json(raw))
        return sorted(jobs, key=lambda j: (j.started_at or datetime.min), reverse=True)


# ── Factory ───────────────────────────────────────────────────────────────────


def make_job_store() -> MemoryJobStore | RedisJobStore:
    """Instantiate and return the configured job store backend."""
    from config import settings

    if settings.JOB_STORE_BACKEND == "redis":
        if not settings.REDIS_URL:
            raise RuntimeError(
                "REDIS_URL must be configured in your environment or .env file "
                "when JOB_STORE_BACKEND is set to 'redis'."
            )
        return RedisJobStore()
    return MemoryJobStore()


job_store = make_job_store()

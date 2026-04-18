"""
services/agents/api_client.py
=============================
Async HTTP client for agent-to-FastAPI communication.

All agents communicate with the FastAPI backend through this module — never
via direct service imports.  This enforces the architecture boundary:

    Agent Layer  →  (HTTP)  →  FastAPI Wrapper  →  Services  →  Core

The client handles:
- Base URL configuration
- Async JSON request/response
- Job polling with progress callbacks
- Timeout and retry logic

Usage
-----
    from services.agents.api_client import api_client, poll_job_until_complete

    result = await api_client.get(f"/api/v1/analysis/{project_id}/results")
    final  = await poll_job_until_complete(job_id, progress_cb=my_callback)
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable, Optional

import httpx

logger = logging.getLogger(__name__)

# FastAPI backend base URL — override with BACKEND_URL env var
_BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# Maximum seconds to wait for a long-running job
_POLL_TIMEOUT_SECONDS = 300  # 5 minutes
_POLL_INTERVAL_SECONDS = 2.0


class StructuralAPIClient:
    """
    Thin async wrapper around ``httpx.AsyncClient`` for structured API calls.

    All methods raise ``httpx.HTTPStatusError`` on non-2xx responses, which
    the agent error handler catches and translates to a ``current_error`` state
    update.

    Attributes
    ----------
    base_url : str
        Root URL of the FastAPI backend.
    timeout : float
        Per-request HTTP timeout in seconds.
    """

    def __init__(self, base_url: str = _BACKEND_URL, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout)

    def _client(self) -> httpx.AsyncClient:
        """Return a configured ``AsyncClient`` instance."""
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self._timeout,
            headers={"Content-Type": "application/json"},
        )

    async def get(self, path: str, **kwargs: Any) -> dict:
        """
        Perform an async GET request and return the parsed JSON body.

        Parameters
        ----------
        path : str
            URL path relative to ``base_url`` (e.g. ``"/api/v1/projects/"``).
        **kwargs
            Additional arguments forwarded to ``httpx.AsyncClient.get``.

        Returns
        -------
        dict
            Parsed JSON response body.

        Raises
        ------
        httpx.HTTPStatusError
            On non-2xx HTTP responses.
        """
        async with self._client() as client:
            response = await client.get(path, **kwargs)
            response.raise_for_status()
            return response.json()

    async def post(self, path: str, json: Optional[dict] = None, **kwargs: Any) -> dict:
        """
        Perform an async POST request and return the parsed JSON body.

        Parameters
        ----------
        path : str
            URL path relative to ``base_url``.
        json : dict | None
            Request body serialised as JSON.
        **kwargs
            Additional arguments forwarded to ``httpx.AsyncClient.post``.

        Returns
        -------
        dict
            Parsed JSON response body.
        """
        async with self._client() as client:
            response = await client.post(path, json=json or {}, **kwargs)
            response.raise_for_status()
            return response.json()

    async def put(self, path: str, json: Optional[dict] = None, **kwargs: Any) -> dict:
        """
        Perform an async PUT request and return the parsed JSON body.

        Parameters
        ----------
        path : str
            URL path relative to ``base_url``.
        json : dict | None
            Request body.
        **kwargs
            Additional arguments.

        Returns
        -------
        dict
        """
        async with self._client() as client:
            response = await client.put(path, json=json or {}, **kwargs)
            response.raise_for_status()
            return response.json()

    async def delete(self, path: str, **kwargs: Any) -> None:
        """
        Perform an async DELETE request.

        Parameters
        ----------
        path : str
            URL path.
        **kwargs
            Additional arguments.
        """
        async with self._client() as client:
            response = await client.delete(path, **kwargs)
            response.raise_for_status()

    async def upload_file(self, path: str, file_path: str) -> dict:
        """
        Upload a file via multipart/form-data to the given path.

        Parameters
        ----------
        path : str
            Upload endpoint path.
        file_path : str
            Absolute path to the file to upload.

        Returns
        -------
        dict
            API response dict.
        """
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self._timeout) as client:
            with open(file_path, "rb") as f:
                response = await client.post(
                    path,
                    files={"file": (file_path.split("/")[-1], f)},
                )
            response.raise_for_status()
            return response.json()


async def poll_job_until_complete(
    job_id: str,
    progress_cb: Optional[Callable[[dict], None]] = None,
    timeout: float = _POLL_TIMEOUT_SECONDS,
    interval: float = _POLL_INTERVAL_SECONDS,
) -> dict:
    """
    Poll ``GET /api/v1/jobs/{job_id}`` until the job reaches a terminal state.

    Intermediate progress snapshots are forwarded to an optional callback so
    the supervisor can stream updates to the IDE chat panel.

    Parameters
    ----------
    job_id : str
        Job identifier to poll.
    progress_cb : Callable[[dict], None] | None
        Optional callback invoked with the JobStatus dict on each poll cycle.
        Use this to push ``agent_log`` entries during long-running operations.
    timeout : float
        Maximum seconds to wait before raising ``TimeoutError``.
    interval : float
        Seconds between poll requests.

    Returns
    -------
    dict
        Final ``JobStatus`` dict when status is ``"complete"``.

    Raises
    ------
    TimeoutError
        If the job does not complete within ``timeout`` seconds.
    RuntimeError
        If the job transitions to ``"failed"`` or ``"cancelled"``.
    """
    elapsed = 0.0
    while elapsed < timeout:
        status = await api_client.get(f"/api/v1/jobs/{job_id}")
        if progress_cb:
            progress_cb(status)

        job_status = status.get("status")
        if job_status == "complete":
            logger.info("Job %s completed.", job_id)
            return status
        if job_status in ("failed", "cancelled"):
            errors = status.get("errors", [])
            raise RuntimeError(
                f"Job {job_id} ended with status '{job_status}'. Errors: {errors}"
            )

        logger.debug(
            "Job %s: %s (%.0f%%) — %s",
            job_id,
            job_status,
            status.get("progress_pct", 0),
            status.get("current_step", ""),
        )
        await asyncio.sleep(interval)
        elapsed += interval

    raise TimeoutError(f"Job {job_id} did not complete within {timeout}s.")


# ── Singleton ─────────────────────────────────────────────────────────────────
api_client = StructuralAPIClient()

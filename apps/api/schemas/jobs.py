"""
schemas/jobs.py
===============
Pydantic model for the async job status system.

Long-running operations (parsing, full analysis, design runs, report generation)
are queued and return immediately with a ``job_id``.  Clients poll the jobs
endpoint to track progress and retrieve the result URL when complete.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class JobStatus(BaseModel):
    """
    Status snapshot for an async job.

    Attributes
    ----------
    job_id : str
        Unique job identifier (e.g. ``"JOB-a1b2c3d4"``).
    job_type : str
        Category of the operation: ``parsing | analysis | design | reporting``.
    status : str
        Current state: ``queued | running | complete | failed | cancelled``.
    progress_pct : float
        Completion percentage in the range 0.0–100.0.
    current_step : str
        Human-readable description of the active processing step.
        Displayed verbatim in the IDE left-panel status log.
    started_at : datetime | None
        UTC timestamp the job began execution, or None if still queued.
    completed_at : datetime | None
        UTC timestamp of completion, or None if still running.
    result_url : str | None
        Relative URL to GET the result payload once status is ``complete``.
    errors : list[str]
        Accumulated error messages.  Non-empty implies status ``failed``.
    """

    job_id: str = Field(..., description="Unique job identifier.")
    job_type: Literal["parsing", "analysis", "design", "reporting"] = Field(
        ..., description="Operation category."
    )
    status: Literal["queued", "running", "complete", "failed", "cancelled"] = Field(
        ..., description="Current job state."
    )
    progress_pct: float = Field(0.0, ge=0.0, le=100.0, description="Completion percentage.")
    current_step: str = Field("", description="Active processing step description.")
    started_at: Optional[datetime] = Field(None, description="UTC start timestamp.")
    completed_at: Optional[datetime] = Field(None, description="UTC completion timestamp.")
    result_url: Optional[str] = Field(None, description="URL for result when complete.")
    errors: list[str] = Field(default_factory=list, description="Error messages.")

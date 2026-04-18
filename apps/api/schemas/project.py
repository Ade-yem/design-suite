"""
schemas/project.py
==================
Pydantic models for the project entity, pipeline state machine, and CRUD responses.

The ``ProjectStatus`` enum defines the pipeline state machine.  Every project advances
through these stages **in order** — the API enforces that a downstream stage cannot be
requested unless the upstream gate has been confirmed.

Pipeline order (ordinal used for comparison)::

    CREATED → FILE_UPLOADED → GEOMETRY_VERIFIED → LOADING_DEFINED →
    ANALYSIS_COMPLETE → DESIGN_COMPLETE → REPORT_GENERATED
"""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Pipeline Status ──────────────────────────────────────────────────────────


class ProjectStatus(IntEnum):
    """
    Ordinal enumeration of the project pipeline state machine.

    Ordinal comparison is used to enforce gate sequencing:
    ``project.status >= ProjectStatus.GEOMETRY_VERIFIED``

    Members
    -------
    CREATED            : Project entity created, no file uploaded yet.
    FILE_UPLOADED      : DXF/PDF file received; async parsing in progress.
    GEOMETRY_VERIFIED  : Human confirmed parsed geometry (Safety Gate 1).
    LOADING_DEFINED    : Load definitions have been submitted and validated.
    ANALYSIS_COMPLETE  : Analysis engine has finished for all members.
    DESIGN_COMPLETE    : Design suite has produced reinforcement schedules.
    REPORT_GENERATED   : At least one report has been successfully generated.
    """

    CREATED = 0
    FILE_UPLOADED = 1
    GEOMETRY_VERIFIED = 2
    LOADING_DEFINED = 3
    ANALYSIS_COMPLETE = 4
    DESIGN_COMPLETE = 5
    REPORT_GENERATED = 6

    def label(self) -> str:
        """Return a human-readable label string for this status."""
        return self.name.lower()


# ─── Request Models ───────────────────────────────────────────────────────────


class ProjectCreate(BaseModel):
    """
    Request body for POST /api/v1/projects/.

    Attributes
    ----------
    name : str
        Human-readable project title (e.g. ``"Greenfield Office Block — Block A"``).
    reference : str
        Internal project / job reference code.
    client : str
        Client or employer name.
    design_code : str
        Primary design code: ``"BS8110"`` or ``"EC2"``.
    """

    name: str = Field(..., min_length=1, max_length=200, description="Project title.")
    reference: str = Field(..., min_length=1, max_length=50, description="Job reference number.")
    client: str = Field("", max_length=200, description="Client name.")
    design_code: str = Field("BS8110", pattern="^(BS8110|EC2)$", description="Primary design code.")


class ProjectUpdate(BaseModel):
    """
    Request body for PUT /api/v1/projects/{project_id}.  All fields are optional.

    Attributes
    ----------
    name : str | None
        Updated project title.
    reference : str | None
        Updated reference code.
    client : str | None
        Updated client name.
    design_code : str | None
        Updated design code.
    """

    name: Optional[str] = Field(None, max_length=200)
    reference: Optional[str] = Field(None, max_length=50)
    client: Optional[str] = Field(None, max_length=200)
    design_code: Optional[str] = Field(None, pattern="^(BS8110|EC2)$")


# ─── Response Models ──────────────────────────────────────────────────────────


class ProjectResponse(BaseModel):
    """
    Full project response for GET /api/v1/projects/{project_id}.

    Attributes
    ----------
    project_id : str
        UUID string uniquely identifying the project.
    name : str
        Project title.
    reference : str
        Job reference code.
    client : str
        Client name.
    design_code : str
        Primary design code.
    pipeline_status : str
        Current pipeline stage label (e.g. ``"geometry_verified"``).
    pipeline_status_ordinal : int
        Numeric ordinal of the pipeline status — useful for frontend progress bars.
    created_at : datetime
        UTC timestamp of project creation.
    updated_at : datetime
        UTC timestamp of last update.
    member_count : int
        Number of structural members currently registered to the project.
    """

    project_id: str
    name: str
    reference: str
    client: str
    design_code: str
    pipeline_status: str
    pipeline_status_ordinal: int
    created_at: datetime
    updated_at: datetime
    member_count: int


class ProjectListItem(BaseModel):
    """
    Lightweight project row for GET /api/v1/projects/ list responses.

    Attributes
    ----------
    project_id : str
        UUID string.
    name : str
        Project title.
    reference : str
        Job reference.
    pipeline_status : str
        Current stage label.
    updated_at : datetime
        Last modified timestamp.
    """

    project_id: str
    name: str
    reference: str
    pipeline_status: str
    updated_at: datetime


class PipelineStatusResponse(BaseModel):
    """
    Response for GET /api/v1/projects/{project_id}/status and
    GET /api/v1/pipeline/{project_id}/status.

    Attributes
    ----------
    project_id : str
        UUID of the project.
    current_stage : str
        Label of the current pipeline stage.
    next_action : str
        Human-readable description of the action needed to advance.
    gates : dict[str, bool]
        Mapping of gate name → confirmed bool.
    blocking_issues : list[str]
        List of human-readable issues preventing advancement.
    completed_members : int
        Count of members with completed analysis results.
    failed_members : int
        Count of members with analysis/design failures.
    last_updated : datetime
        Timestamp of the most recent state change.
    """

    project_id: str
    current_stage: str
    next_action: str
    gates: dict[str, bool]
    blocking_issues: list[str]
    completed_members: int
    failed_members: int
    last_updated: datetime


class BaseResponse(BaseModel):
    """
    Envelope wrapper returned by all mutating endpoints.

    Attributes
    ----------
    success : bool
        Whether the operation succeeded.
    timestamp : datetime
        UTC timestamp of the response.
    project_id : str
        Project the response is scoped to.
    data : Any
        Payload — varies by endpoint.
    warnings : list[str]
        Non-fatal warnings generated during processing.
    """

    success: bool
    timestamp: datetime
    project_id: str
    data: Any
    warnings: list[str] = []

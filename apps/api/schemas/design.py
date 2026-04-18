"""
schemas/design.py
=================
Pydantic models for the design router — override requests, re-run triggers,
and result envelopes wrapping the Design Suite outputs.

Units
-----
- Forces  : kN
- Moments : kNm
- Areas   : mm²
- Lengths : m (spans) or mm (section dimensions)
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ─── Request Models ───────────────────────────────────────────────────────────


class DesignRunRequest(BaseModel):
    """
    Request body for POST /api/v1/design/{project_id}/run and per-type endpoints.

    Attributes
    ----------
    member_ids : list[str] | None
        IDs of members to design.  ``None`` → design all members.
    design_code : str | None
        Override the project-level design code for this run only.
    allow_iteration : bool
        If True, permits the designer to feed back to the analyser when a size change
        exceeds the self-weight tolerance. Default True.
    """

    member_ids: Optional[list[str]] = Field(
        None, description="Member subset — None designs all members."
    )
    design_code: Optional[Literal["BS8110", "EC2"]] = Field(
        None, description="Per-run code override."
    )
    allow_iteration: bool = Field(
        True, description="Permit feedback loops to the analyser on size changes."
    )


class MemberDesignOverride(BaseModel):
    """
    Direct geometry / parameter override for a single member.
    Used by PUT /api/v1/design/{project_id}/member/{member_id}.

    This is the key endpoint called by the IDE agent when the engineer types
    "change beam B1 to 300×600" in the chat panel.

    Attributes
    ----------
    b_mm : float | None
        New section width in mm.
    h_mm : float | None
        New section total depth in mm.
    cover_mm : float | None
        Updated nominal cover in mm.
    fck_MPa : float | None
        Updated characteristic compressive strength in MPa (EC2 notation).
    fcu_MPa : float | None
        Updated characteristic cube strength in MPa (BS 8110 notation).
    fy_MPa : float | None
        Updated main reinforcement yield strength in MPa.
    meta_updates : dict[str, Any]
        Any other member-type-specific parameter updates (e.g. slab_type).
    reason : str
        Engineering justification preserved in the calculation log.
    """

    b_mm: Optional[float] = Field(None, gt=0, description="New section width in mm.")
    h_mm: Optional[float] = Field(None, gt=0, description="New section depth in mm.")
    cover_mm: Optional[float] = Field(None, gt=0, description="Updated nominal cover in mm.")
    fck_MPa: Optional[float] = Field(None, gt=0, description="fck (cylinder) in MPa.")
    fcu_MPa: Optional[float] = Field(None, gt=0, description="fcu (cube) in MPa.")
    fy_MPa: Optional[float] = Field(None, gt=0, description="Main rebar fy in MPa.")
    meta_updates: dict[str, Any] = Field(
        default_factory=dict, description="Additional parameter overrides."
    )
    reason: str = Field("", description="Engineering justification (logged).")


# ─── Response Models ──────────────────────────────────────────────────────────


class DesignJobStarted(BaseModel):
    """
    Immediate response for async design run endpoints.

    Attributes
    ----------
    job_id : str
        Job identifier — poll ``status_url`` for progress.
    status_url : str
        Relative URL to poll for status.
    message : str
        Human-readable status message.
    """

    job_id: str
    status_url: str
    message: str


class MemberDesignOverrideResponse(BaseModel):
    """
    Response for PUT /api/v1/design/{project_id}/member/{member_id}.

    Attributes
    ----------
    result : dict[str, Any]
        Updated design result for the affected member.
    warning : str | None
        Non-None if the self-weight changed >5%  — prompts re-analysis.
    reanalysis_url : str | None
        Relative URL to trigger re-analysis for this member if required.
    """

    result: dict[str, Any]
    warning: Optional[str] = None
    reanalysis_url: Optional[str] = None


class DesignResultsResponse(BaseModel):
    """
    Response for GET /api/v1/design/{project_id}/results.

    Attributes
    ----------
    project_id : str
        Project identifier.
    design_id : str
        Unique design run identifier.
    design_code : str
        Code used during design.
    member_count : int
        Total number of designed members.
    members : list[dict[str, Any]]
        List of DesignedMember dicts produced by the Design Suite.
    generated_at : str
        ISO 8601 timestamp.
    """

    project_id: str
    design_id: str
    design_code: str
    member_count: int
    members: list[dict[str, Any]]
    generated_at: str

"""
schemas/analysis.py
===================
Pydantic models for the analysis router — options, async job references,
and result envelopes wrapping the Analysis Engine outputs.

Units
-----
- Forces  : kN
- Moments : kNm
- Lengths : m
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ─── Request / Options ────────────────────────────────────────────────────────


class AnalysisOptions(BaseModel):
    """
    Solver configuration passed to POST /api/v1/analysis/{project_id}/run.

    Attributes
    ----------
    pattern_loading : bool
        If True, runs all three EC2 / BS 8110 load arrangements (Full / Alternate / Adjacent).
    self_weight_iteration : bool
        If True, iterates member sizes until self-weight contribution converges.
    max_iterations : int
        Maximum number of self-weight convergence loops (default 5).
    convergence_tolerance : float
        Fractional change threshold below which iteration is deemed converged (default 0.02 = 2%).
    member_ids : list[str] | None
        Subset of member IDs to analyse.  ``None`` → analyse all members.
    """

    pattern_loading: bool = Field(True, description="Run all EC2/BS8110 load arrangements.")
    self_weight_iteration: bool = Field(True, description="Iterate until self-weight converges.")
    max_iterations: int = Field(5, ge=1, le=20, description="Convergence iteration limit.")
    convergence_tolerance: float = Field(
        0.02, gt=0, lt=1.0, description="Fractional convergence threshold (e.g. 0.02 = 2%)."
    )
    member_ids: Optional[list[str]] = Field(
        None, description="Member ID subset — None runs all members."
    )


class SingleMemberAnalysisRequest(BaseModel):
    """
    Request body for POST /api/v1/analysis/{project_id}/{member_type} endpoints.

    Attributes
    ----------
    member_ids : list[str]
        IDs of the specific members to analyse.
    options : AnalysisOptions
        Solver configuration overrides.
    """

    member_ids: list[str] = Field(..., min_length=1, description="Member IDs to analyse.")
    options: AnalysisOptions = Field(default_factory=AnalysisOptions)


# ─── Job reference response ───────────────────────────────────────────────────


class AnalysisJobStarted(BaseModel):
    """
    Immediate response for async analysis endpoints.

    Attributes
    ----------
    job_id : str
        Async job identifier — poll ``status_url`` for progress.
    status_url : str
        Relative URL to GET for job progress.
    message : str
        Human-readable status message for the IDE chat panel.
    """

    job_id: str
    status_url: str
    message: str


# ─── Progress model (returned by status polling) ──────────────────────────────


class AnalysisProgress(BaseModel):
    """
    Progress snapshot returned by GET /api/v1/analysis/{project_id}/status/{job_id}.

    Attributes
    ----------
    total_members : int
        Total number of members included in the analysis run.
    completed : int
        Members whose solver has returned a result.
    current_member : str
        ID of the member currently being processed.
    current_stage : str
        Human-readable description of the active solver step.
    """

    total_members: int
    completed: int
    current_member: str = ""
    current_stage: str = ""


class AnalysisStatusResponse(BaseModel):
    """
    Full status response for GET /api/v1/analysis/{project_id}/status/{job_id}.

    Attributes
    ----------
    job_id : str
        Job identifier.
    status : str
        One of ``queued | running | complete | failed``.
    progress : AnalysisProgress
        Current progress snapshot.
    errors : list[str]
        Member-level error messages collected during the run.
    result_url : str | None
        URL to GET analysis results when status is ``complete``.
    """

    job_id: str
    status: Literal["queued", "running", "complete", "failed"]
    progress: AnalysisProgress
    errors: list[str] = []
    result_url: Optional[str] = None


# ─── Results wrappers ─────────────────────────────────────────────────────────


class AnalysisResultsResponse(BaseModel):
    """
    Response for GET /api/v1/analysis/{project_id}/results.

    Attributes
    ----------
    project_id : str
        Project identifier.
    analysis_id : str
        Unique analysis run identifier (UUID).
    design_code : str
        Code used during analysis.
    member_count : int
        Total number of member results.
    members : list[dict[str, Any]]
        List of MemberAnalysisResult dicts.
    generated_at : str
        ISO 8601 timestamp.
    """

    project_id: str
    analysis_id: str
    design_code: str
    member_count: int
    members: list[dict[str, Any]]
    generated_at: str

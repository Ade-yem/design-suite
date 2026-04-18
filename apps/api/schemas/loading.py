"""
schemas/loading.py
==================
Pydantic models for the loading router — defining, validating and retrieving
structural load definitions.

Units
-----
- Distributed loads : kN/m² (area) or kN/m (line)
- Point loads       : kN
- Moments           : kNm
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ─── Load sub-models ──────────────────────────────────────────────────────────


class DeadLoadDefinition(BaseModel):
    """
    Characteristic dead (permanent) load components applied to floor slabs.

    Attributes
    ----------
    finishes_kNm2 : float
        Floor finishes load in kN/m².
    screed_kNm2 : float
        Screed / levelling layer load in kN/m².
    services_kNm2 : float
        M&E services load in kN/m².
    partitions_kNm2 : float
        Moveable partitions treated as quasi-permanent dead load in kN/m².
    cladding_kNm : float | None
        Perimeter cladding line load in kN/m (perimeter beams only).
    """

    finishes_kNm2: float = Field(1.5, ge=0, description="Floor finishes in kN/m².")
    screed_kNm2: float = Field(0.8, ge=0, description="Screed layer in kN/m².")
    services_kNm2: float = Field(0.5, ge=0, description="M&E services in kN/m².")
    partitions_kNm2: float = Field(1.0, ge=0, description="Moveable partitions in kN/m².")
    cladding_kNm: Optional[float] = Field(
        None, ge=0, description="Cladding line load in kN/m (perimeter beams only)."
    )


class ImposedLoadDefinition(BaseModel):
    """
    Characteristic imposed (variable) load components.

    Attributes
    ----------
    floor_qk_kNm2 : float
        Floor imposed load from occupancy table in kN/m².
    roof_qk_kNm2 : float
        Roof imposed load in kN/m².
    stair_qk_kNm2 : float
        Staircase imposed load in kN/m².
    """

    floor_qk_kNm2: float = Field(..., ge=0, description="Floor Qk from occupancy table in kN/m².")
    roof_qk_kNm2: float = Field(0.6, ge=0, description="Roof Qk in kN/m².")
    stair_qk_kNm2: float = Field(3.0, ge=0, description="Staircase Qk in kN/m².")


class MemberLoadOverride(BaseModel):
    """
    Per-member exception for load definitions.

    Attributes
    ----------
    member_id : str
        Target member identifier.
    dead_extra_kNm2 : float | None
        Additional dead load to add on top of the global definition (kN/m²).
    imposed_override_kNm2 : float | None
        Replacement Qk value for this member specifically (kN/m²).
    notes : str
        Reason for the override, preserved in the calculation log.
    """

    member_id: str = Field(..., description="Target member ID.")
    dead_extra_kNm2: Optional[float] = Field(None, ge=0, description="Extra dead load in kN/m².")
    imposed_override_kNm2: Optional[float] = Field(
        None, ge=0, description="Override imposed load in kN/m²."
    )
    notes: str = Field("", description="Reason for override (logged).")


# ─── Request models ───────────────────────────────────────────────────────────


class LoadDefinitionRequest(BaseModel):
    """
    Request body for POST /api/v1/loading/{project_id}/define.

    Attributes
    ----------
    design_code : str
        Design code used for load combination factors (``"BS8110"`` or ``"EC2"``).
    occupancy_category : str
        Occupancy classification from the standard occupancy table.
    dead_loads : DeadLoadDefinition
        Characteristic dead load components.
    imposed_loads : ImposedLoadDefinition
        Characteristic imposed load components.
    member_overrides : list[MemberLoadOverride]
        Per-member exceptions to the global load definition.
    """

    design_code: Literal["BS8110", "EC2"] = Field("BS8110", description="Load combination code.")
    occupancy_category: Literal[
        "residential", "office", "retail", "roof_accessible",
        "roof_non_accessible", "stairs", "custom"
    ] = Field("office", description="Occupancy category for imposed load lookup.")
    dead_loads: DeadLoadDefinition = Field(default_factory=DeadLoadDefinition)
    imposed_loads: ImposedLoadDefinition
    member_overrides: list[MemberLoadOverride] = Field(
        default_factory=list, description="Per-member load exceptions."
    )


class MemberLoadUpdate(BaseModel):
    """
    Request body for PUT /api/v1/loading/{project_id}/member/{member_id}.

    Attributes
    ----------
    dead_extra_kNm2 : float | None
        Additional dead load increment in kN/m².
    imposed_override_kNm2 : float | None
        Replacement imposed floor load in kN/m².
    notes : str
        Engineering justification for the change.
    """

    dead_extra_kNm2: Optional[float] = Field(None, ge=0)
    imposed_override_kNm2: Optional[float] = Field(None, ge=0)
    notes: str = ""


# ─── Response models ──────────────────────────────────────────────────────────


class LoadCombinationResult(BaseModel):
    """
    Factored design load envelope for a single span.

    Attributes
    ----------
    span_id : str
        Span identifier.
    n_uls_kNm2 : float
        Ultimate limit state design load in kN/m².
    n_sls_kNm2 : float
        Serviceability limit state design load in kN/m².
    combination_label : str
        Load combination expression used (e.g. ``"1.4Gk + 1.6Qk"``).
    """

    span_id: str
    n_uls_kNm2: float
    n_sls_kNm2: float
    combination_label: str


class LoadingOutputResponse(BaseModel):
    """
    Full loading output for GET /api/v1/loading/{project_id}/output.

    Attributes
    ----------
    project_id : str
        Project identifier.
    design_code : str
        Code used for combination factors.
    members : list[dict[str, Any]]
        List of MemberLoadOutput dicts as produced by the Loading Module serializer.
    generated_at : str
        ISO 8601 timestamp.
    """

    project_id: str
    design_code: str
    members: list[dict[str, Any]]
    generated_at: str


class LoadValidationResult(BaseModel):
    """
    Response for POST /api/v1/loading/{project_id}/validate.

    Attributes
    ----------
    valid : bool
        True if all load definitions pass validation.
    errors : list[str]
        Field-level validation errors preventing member analysis.
    warnings : list[str]
        Non-blocking issues (e.g. unusually high load values flagged for review).
    """

    valid: bool
    errors: list[str]
    warnings: list[str]

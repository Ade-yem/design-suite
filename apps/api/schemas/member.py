"""
schemas/member.py
=================
Shared structural member geometry schemas used by the loading, analysis and design routers.

Units
-----
- Lengths : metres (m)
- Dimensions : millimetres (mm) for section properties, metres for span lengths
- Stresses : MPa
- Areas : mm²
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class SectionDimensions(BaseModel):
    """
    Rectangular cross-section dimensions.

    Attributes
    ----------
    b_mm : float
        Section width in millimetres.
    h_mm : float
        Section total depth in millimetres.
    cover_mm : float
        Nominal cover to main reinforcement in millimetres.
    """

    b_mm: float = Field(..., gt=0, description="Section width in mm.")
    h_mm: float = Field(..., gt=0, description="Section total depth in mm.")
    cover_mm: float = Field(25.0, gt=0, description="Nominal cover in mm.")


class MaterialProperties(BaseModel):
    """
    Concrete and steel material properties.

    Attributes
    ----------
    fck_MPa : float
        Characteristic cylinder compressive strength (EC2) in MPa.
    fcu_MPa : float
        Characteristic cube compressive strength (BS 8110) in MPa.
    fy_MPa : float
        Characteristic yield strength of main reinforcement in MPa.
    fyw_MPa : float
        Characteristic yield strength of shear links in MPa.
    Ec_GPa : float
        Elastic modulus of concrete in GPa.
    """

    fck_MPa: float = Field(25.0, gt=0, description="fck (cylinder) in MPa.")
    fcu_MPa: float = Field(30.0, gt=0, description="fcu (cube) in MPa.")
    fy_MPa: float = Field(500.0, gt=0, description="Main rebar fy in MPa.")
    fyw_MPa: float = Field(500.0, gt=0, description="Link rebar fyv in MPa.")
    Ec_GPa: float = Field(30.0, gt=0, description="Concrete elastic modulus in GPa.")


class MemberGeometry(BaseModel):
    """
    Full geometry descriptor for a single structural member.

    Attributes
    ----------
    member_id : str
        Unique identifier assigned during geometry extraction.
    member_type : str
        Classification: beam | slab | column | wall | footing | staircase.
    floor_level : str
        Floor/storey label (e.g. ``"G"``  or ``"L02"``).
    section : SectionDimensions
        Cross-section dimensions.
    material : MaterialProperties
        Concrete and steel properties.
    spans_m : list[float]
        Span lengths in metres (one entry per span for continuous members).
    meta : dict[str, Any]
        Additional member-type-specific geometry data (slab_type, end_conditions, etc.).
    """

    member_id: str = Field(..., description="Unique member identifier.")
    member_type: Literal["beam", "slab", "column", "wall", "footing", "staircase"] = Field(
        ..., description="Structural member type."
    )
    floor_level: str = Field("G", description="Floor/storey label.")
    section: SectionDimensions
    material: MaterialProperties = MaterialProperties()
    spans_m: list[float] = Field(default_factory=list, description="Span lengths in metres.")
    meta: dict[str, Any] = Field(
        default_factory=dict, description="Type-specific geometry metadata."
    )


class MemberGeometryPatch(BaseModel):
    """
    Partial update payload for PUT /api/v1/design/{project_id}/member/{member_id}.
    All fields are optional — only those supplied are applied.

    Attributes
    ----------
    section : SectionDimensions | None
        Replacement section dimensions.
    material : MaterialProperties | None
        Replacement material properties.
    meta : dict[str, Any] | None
        Merged metadata overrides.
    """

    section: Optional[SectionDimensions] = None
    material: Optional[MaterialProperties] = None
    meta: Optional[dict[str, Any]] = None

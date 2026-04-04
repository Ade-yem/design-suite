"""
Beam Section Model
==================
Structured input / derived-geometry object for BS 8110-1:1997 beam design.

Keeping section models here (``models/calculations/``) separates the *what*
(the cross-section data) from the *how* (the calculation logic in
``services/calculations/bs8110/``).
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BeamSection:
    """
    Represents a beam cross-section with all geometric and material properties.

    Effective depth ``d`` and compression-steel depth ``d_prime`` are *derived*
    automatically from the cover, link diameter, and bar diameters — they
    should not be set manually.

    Parameters
    ----------
    b : float
        Web width (mm).
    h : float
        Overall section depth (mm).
    cover : float
        Nominal concrete cover to main bars (mm). BS 8110 Table 3.3 / Cl 3.3.1.
    fcu : float
        Characteristic cube compressive strength (N/mm²).
    fy : float
        Characteristic yield strength of tension reinforcement (N/mm²).
    fyv : float
        Characteristic yield strength of shear links (N/mm²).
    link_dia : float
        Diameter of shear links (mm). Default 8 mm.
    bar_dia : float
        Assumed main tension bar diameter used to derive ``d`` (mm).
        Default 20 mm.
    comp_bar_dia : float
        Assumed compression bar diameter used to derive ``d_prime`` (mm).
        Default 16 mm.
    section_type : str
        ``"rectangular"`` or ``"flanged"``.
    support_condition : str
        ``"simple"``, ``"continuous"``, or ``"cantilever"``.
    bf : float, optional
        Effective flange width (mm). Required when ``section_type == "flanged"``.
    hf : float, optional
        Flange (slab) thickness (mm). Required when ``section_type == "flanged"``.
    beta_b : float
        Moment redistribution factor (0.70 ≤ β_b ≤ 1.0). Default 1.0
        (no redistribution). BS 8110 Cl 3.2.2.1.

    Derived Attributes
    ------------------
    d : float
        Effective depth = h − cover − link_dia − bar_dia/2  (BS 8110 Cl 3.3.3)
    d_prime : float
        Depth to compression-bar centroid = cover + link_dia + comp_bar_dia/2
    As_min : float
        Minimum tensile steel area per Table 3.25 (mm²).
    As_max : float
        Maximum steel area per Cl 3.12.6.1 (4 % of b·h) (mm²).
    """

    # ------------------------------------------------------------------ inputs
    b: float
    h: float
    cover: float
    fcu: float
    fy: float
    fyv: float
    link_dia: float = 8.0
    bar_dia: float = 20.0
    comp_bar_dia: float = 16.0
    section_type: str = "rectangular"
    support_condition: str = "simple"
    bf: Optional[float] = None
    hf: Optional[float] = None
    beta_b: float = 1.0

    # --------------------------------------------------------------- derived
    d: float = field(init=False)
    d_prime: float = field(init=False)
    As_min: float = field(init=False)
    As_max: float = field(init=False)

    def __post_init__(self):
        # Effective depth to centroid of tension bars  (BS 8110 Cl 3.3.3)
        self.d = self.h - self.cover - self.link_dia - self.bar_dia / 2.0

        # Depth to centroid of compression bars
        self.d_prime = self.cover + self.link_dia + self.comp_bar_dia / 2.0

        # Minimum steel — BS 8110 Table 3.25
        #   0.13 % b·h for fy = 460 N/mm²
        #   0.15 % b·h for fy = 250 N/mm²
        min_pct = 0.13 if self.fy >= 460 else 0.15
        self.As_min = (min_pct / 100.0) * self.b * self.h

        # Maximum steel — BS 8110 Cl 3.12.6.1  (4 % gross area)
        self.As_max = 0.04 * self.b * self.h

        self._validate()

    # ---------------------------------------------------------------- helpers
    def _validate(self):
        if self.d <= 0:
            raise ValueError(
                f"Derived effective depth d = {self.d:.1f} mm ≤ 0. "
                "Check cover, link diameter, and overall depth h."
            )
        if self.section_type == "flanged":
            if self.bf is None or self.hf is None:
                raise ValueError(
                    "bf (effective flange width) and hf (flange thickness) "
                    "must both be supplied for flanged beams."
                )
            if self.bf < self.b:
                raise ValueError(
                    f"bf ({self.bf} mm) must be ≥ web width b ({self.b} mm)."
                )
            if self.hf >= self.h:
                raise ValueError(
                    f"hf ({self.hf} mm) must be < overall depth h ({self.h} mm)."
                )
        if not (0.70 <= self.beta_b <= 1.0):
            raise ValueError(
                f"beta_b = {self.beta_b} is outside the permitted range [0.70, 1.00] "
                "(BS 8110 Cl 3.2.2.1)."
            )

    def summary(self) -> str:
        lines = [
            f"BeamSection ({self.section_type}, {self.support_condition})",
            f"  b × h          : {self.b} × {self.h} mm",
            f"  Cover          : {self.cover} mm",
            f"  Link / bar dia : H{int(self.link_dia)} / H{int(self.bar_dia)}",
            f"  d  (effective) : {self.d:.1f} mm",
            f"  d' (comp. bar) : {self.d_prime:.1f} mm",
            f"  fcu / fy / fyv : {self.fcu} / {self.fy} / {self.fyv} N/mm²",
            f"  As,min         : {self.As_min:.1f} mm²",
            f"  As,max         : {self.As_max:.1f} mm²",
        ]
        if self.section_type == "flanged":
            lines += [
                f"  bf (flange)    : {self.bf} mm",
                f"  hf (flange t.) : {self.hf} mm",
            ]
        if self.beta_b < 1.0:
            lines.append(f"  β_b (redist.)  : {self.beta_b}")
        return "\n".join(lines)

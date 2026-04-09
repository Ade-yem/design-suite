"""
Staircase Section Model
=======================
Structured input object for BS 8110-1:1997 Clause 3.10 staircase design.

Geometry
--------
The staircase is modelled as an inclined one-way spanning slab.  All
dimensions are "on plan" (horizontal) unless noted otherwise.

Design philosophy (BS 8110 Cl 3.10):
  * The stair waist (slab softfit to nosing line) is the structural member.
  * Loads are applied as horizontal UDLs (plan loads) per Cl 3.10.1.2.
  * The effective span is measured on plan between centrelines of supports.
  * A stiffness-based effective depth is allowed per Cl 3.10.1.4.
"""

from dataclasses import dataclass, field
from typing import Optional
import math


@dataclass
class StaircaseSection:
    """
    Represents a straight reinforced concrete staircase flight.

    Parameters
    ----------
    waist         : Waist thickness — perpendicular to the soffit (mm)
    tread         : Horizontal tread dimension (mm)
    riser         : Vertical riser dimension (mm)
    num_steps     : Number of steps in the flight
    span          : Effective span on plan (mm)  — centre-to-centre of supports
    width         : Width of staircase flight (mm)  — used for load input
    cover         : Nominal concrete cover to main bars (mm)
    fcu           : Characteristic cube strength (N/mm²)
    fy            : Characteristic steel yield strength (N/mm²)
    support_condition : "simple" | "continuous" — governs deflection ratio
    bar_dia       : Assumed main longitudinal bar diameter (mm)
    bar_dia_dist  : Assumed distribution bar diameter (mm)
    link_dia      : No links needed for slab-type; kept for completeness (mm)
    beta_b        : Moment redistribution factor (0.7–1.0); default 1.0
    """

    waist: float          # Waist thickness, perpendicular to soffit (mm)
    tread: float          # Horizontal tread (mm)
    riser: float          # Vertical riser (mm)
    num_steps: int        # Number of steps in the flight
    span: float           # Effective span on plan (mm)
    width: float = 1000.0 # Width of flight for 1m-strip design (mm); set 1000 for /m
    cover: float = 25.0
    fcu: float = 30.0
    fy: float = 500.0
    support_condition: str = "simple"
    bar_dia: float = 12.0
    bar_dia_dist: float = 8.0
    beta_b: float = 1.0

    # ---- derived geometry (computed in __post_init__) ----
    angle: float = field(init=False)         # Inclination angle α (radians)
    cos_alpha: float = field(init=False)
    going: float = field(init=False)         # Hypotenuse of one step (mm)
    mean_thickness: float = field(init=False)# Average structural thickness on slope (mm)
    d: float = field(init=False)             # Effective depth (mm)
    d_dist: float = field(init=False)        # Effective depth for distribution steel
    As_min: float = field(init=False)        # Minimum steel area (mm²/m)
    As_max: float = field(init=False)        # Maximum steel area (mm²/m)

    def __post_init__(self):
        # ---- Geometry -------------------------------------------------------
        # α = angle of inclination to horizontal
        self.angle = math.atan(self.riser / self.tread)
        self.cos_alpha = math.cos(self.angle)

        # Hypotenuse length of one step (along the slope)
        self.going = math.sqrt(self.tread ** 2 + self.riser ** 2)

        # Mean overall thickness on slope (for self-weight)
        # = waist + 0.5 × riser (triangular step contribution)
        self.mean_thickness = self.waist + 0.5 * self.riser

        # ---- Effective depth -----------------------------------------------
        # Cl 3.10.1.4: d measured perpendicular to soffit
        # On plan, effective depth = waist – cover – bar_dia/2 (approx horizontal component)
        self.d = self.waist - self.cover - (self.bar_dia / 2.0)

        # Distribution steel is placed over the main bars
        self.d_dist = self.d - self.bar_dia / 2.0 - self.bar_dia_dist / 2.0

        # ---- Reinforcement limits (Table 3.25: slab limits) ----------------
        # Use 1m width (b=1000) for per-metre values
        b_eff = 1000.0
        min_pct = 0.13 if self.fy >= 460 else 0.24
        self.As_min = (min_pct / 100.0) * b_eff * self.waist
        self.As_max = 0.04 * b_eff * self.waist

        self._validate()

    def _validate(self):
        if self.d <= 0:
            raise ValueError(
                f"Effective depth d = {self.d:.1f} mm ≤ 0. "
                "Increase waist thickness or reduce cover."
            )
        if self.tread <= 0 or self.riser <= 0:
            raise ValueError("Tread and riser must be positive.")
        if self.span <= 0:
            raise ValueError("Effective span must be positive.")
        if self.riser > 220 or self.tread < 220:
            import warnings
            warnings.warn(
                f"Step geometry (R={self.riser}mm, T={self.tread}mm) may not "
                "satisfy Building Regulations (R ≤ 220mm, T ≥ 220mm for public)."
            )

    @property
    def slope_length(self) -> float:
        """Total length along slope of the flight (mm)."""
        return self.num_steps * self.going

    @property
    def rise_height(self) -> float:
        """Total vertical rise of the flight (mm)."""
        return self.num_steps * self.riser

    def summary(self) -> str:
        lines = [
            f"StaircaseSection ({self.support_condition})",
            f"  Flight geometry : {self.num_steps} steps, R={self.riser}mm T={self.tread}mm",
            f"  α (inclination) : {math.degrees(self.angle):.1f}°",
            f"  Waist           : {self.waist} mm",
            f"  Mean thickness  : {self.mean_thickness:.1f} mm",
            f"  Eff. span (plan): {self.span:.0f} mm",
            f"  Cover           : {self.cover} mm",
            f"  d (effective)   : {self.d:.1f} mm",
            f"  fcu / fy        : {self.fcu} / {self.fy} N/mm²",
            f"  As,min / As,max : {self.As_min:.1f} / {self.As_max:.1f} mm²/m",
        ]
        return "\n".join(lines)

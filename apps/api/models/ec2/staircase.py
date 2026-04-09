"""
EC2 Staircase Section Model
===========================
Structured input object for BS EN 1992-1-1:2004 staircase design.

Geometry
--------
The staircase is modelled as an inclined one-way spanning slab. All
dimensions are "on plan" (horizontal) unless noted otherwise.

Design philosophy (EC2):
  * The stair waist (slab soffit to nosing line) is the structural member.
  * Loads are applied as horizontal UDLs (plan loads).
  * The effective span is measured on plan between centrelines of supports.
"""

from dataclasses import dataclass, field
import math

GAMMA_C: float = 1.50
GAMMA_S: float = 1.15

@dataclass
class EC2StaircaseSection:
    """
    Represents a straight reinforced concrete staircase flight per Eurocode 2.

    Parameters
    ----------
    waist         : Waist thickness — perpendicular to the soffit (mm)
    tread         : Horizontal tread dimension (mm)
    riser         : Vertical riser dimension (mm)
    num_steps     : Number of steps in the flight
    span          : Effective span on plan (mm)  — centre-to-centre of supports
    width         : Width of staircase flight (mm)  — used for load input
    cover         : Nominal concrete cover to main bars (mm)
    fck           : Characteristic cylinder strength (N/mm²)
    fyk           : Characteristic steel yield strength (N/mm²)
    support_condition : "simple" | "continuous" | "cantilever"
    bar_dia       : Assumed main longitudinal bar diameter (mm)
    bar_dia_dist  : Assumed distribution bar diameter (mm)
    delta         : Moment redistribution factor (0.7–1.0); default 1.0
    is_end_span   : True if end span of a continuous system (affects L/d K factor)
    """

    waist: float
    tread: float
    riser: float
    num_steps: int
    span: float
    width: float = 1000.0
    cover: float = 25.0
    fck: float = 30.0
    fyk: float = 500.0
    support_condition: str = "simple"
    bar_dia: float = 12.0
    bar_dia_dist: float = 8.0
    delta: float = 1.0
    is_end_span: bool = False

    # ---- derived geometry (computed in __post_init__) ----
    angle: float = field(init=False)         # Inclination angle α (radians)
    cos_alpha: float = field(init=False)
    going: float = field(init=False)         # Hypotenuse of one step (mm)
    mean_thickness: float = field(init=False)# Average structural thickness on slope (mm)
    d: float = field(init=False)             # Effective depth (mm)
    d_dist: float = field(init=False)        # Effective depth for distribution steel
    fctm: float = field(init=False)          # Mean tensile strength (N/mm²)
    As_min: float = field(init=False)        # Minimum steel area (mm²/m)
    As_max: float = field(init=False)        # Maximum steel area (mm²/m)

    def __post_init__(self):
        # ---- Geometry -------------------------------------------------------
        self.angle = math.atan(self.riser / self.tread)
        self.cos_alpha = math.cos(self.angle)

        self.going = math.sqrt(self.tread ** 2 + self.riser ** 2)

        # Mean overall thickness on slope
        self.mean_thickness = self.waist + 0.5 * self.riser * self.cos_alpha

        # ---- Effective depth -----------------------------------------------
        self.d = self.waist - self.cover - (self.bar_dia / 2.0)
        self.d_dist = self.d - self.bar_dia / 2.0 - self.bar_dia_dist / 2.0

        # ---- Concrete properties -------------------------------------------
        if self.fck <= 50:
            self.fctm = 0.30 * self.fck ** (2.0 / 3.0)
        else:
            self.fctm = 2.12 * math.log(1.0 + (self.fck + 8.0) / 10.0)

        # ---- Reinforcement limits (EC2 Cl 9.2.1.1) -------------------------
        b_t = 1000.0
        self.As_min = max(
            0.26 * (self.fctm / self.fyk) * b_t * self.d,
            0.0013 * b_t * self.d,
        )
        self.As_max = 0.04 * b_t * self.waist

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
            f"EC2StaircaseSection ({self.support_condition})",
            f"  Flight geometry : {self.num_steps} steps, R={self.riser}mm T={self.tread}mm",
            f"  α (inclination) : {math.degrees(self.angle):.1f}°",
            f"  Waist           : {self.waist} mm",
            f"  Mean thickness  : {self.mean_thickness:.1f} mm",
            f"  Eff. span (plan): {self.span:.0f} mm",
            f"  Cover           : {self.cover} mm",
            f"  d (effective)   : {self.d:.1f} mm",
            f"  fck / fyk       : {self.fck} / {self.fyk} N/mm²",
            f"  As_min / As_max : {self.As_min:.1f} / {self.As_max:.1f} mm²/m",
        ]
        return "\n".join(lines)

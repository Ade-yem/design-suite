"""
EC2 Wall Section Model
======================
BS EN 1992-1-1:2004 – Clause 9.6: Reinforced Concrete Walls

Provides the ``EC2WallSection`` dataclass representing a 1 m wide strip of a 
reinforced concrete wall for design.

Geometry
--------
  * ``h``   — wall thickness (mm). Suggested minimum 150 mm in practice.
  * ``l_w`` — wall horizontal length (mm). Used for shear.
  * ``l_0`` — effective height of the wall (mm) (Cl 5.8.3.2).

Reinforcement limits (Cl 9.6.2 & 9.6.3)
---------------------------------------
  * As,vmin = 0.002 * Ac (Cl 9.6.2(1))
  * As,vmax = 0.04 * Ac (Cl 9.6.2(1))
  * As,hmin = max(0.25 * As_v_prov, 0.001 * Ac) (Cl 9.6.3(1))
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

GAMMA_C: float = 1.50
GAMMA_S: float = 1.15

@dataclass
class EC2WallSection:
    h: float            # Wall thickness (mm)
    l_w: float          # Horizontal wall length (mm)
    l_0: float          # Effective height (mm)
    fck: float          # Cylinder strength (N/mm²)
    fyk: float = 500.0  # Steel yield strength (N/mm²)
    cover: float = 35.0 # Cover to face of vertical bars (mm)
    bar_dia: float = 12.0
    braced: bool = True

    # Derived
    d: float = field(init=False)
    fcd: float = field(init=False)
    fyd: float = field(init=False)
    As_min_v: float = field(init=False)
    As_max_v: float = field(init=False)
    As_min_h: float = field(init=False)

    def __post_init__(self):
        self.d = self.h - self.cover - self.bar_dia / 2.0
        self.fcd = 0.85 * self.fck / GAMMA_C
        self.fyd = self.fyk / GAMMA_S

        # Min vertical steel (0.002 Ac)
        self.As_min_v = 0.002 * 1000.0 * self.h
        
        # Max vertical steel (0.04 Ac outside lap zones)
        self.As_max_v = 0.04 * 1000.0 * self.h

        # Min horizontal steel (0.001 Ac) - later clamped to 25% of provided vertical
        self.As_min_h = 0.001 * 1000.0 * self.h

        self._validate()

    def _validate(self):
        errors = []
        if self.h < 100:
            errors.append(f"Wall thickness h ({self.h} mm) < 100 mm.")
        if self.d <= 0:
            errors.append("Effective depth d <= 0. Decrease cover or increase h.")
        if self.l_0 <= 0 or self.l_w <= 0:
            errors.append("Effective dimensions must be positive.")
        if errors:
            raise ValueError("EC2WallSection validation errors:\n  " + "\n  ".join(errors))

    def summary(self) -> str:
        lines = [
            f"EC2WallSection ({'Braced' if self.braced else 'Unbraced'})",
            f"  h × l_w       : {self.h} × {self.l_w:.0f} mm",
            f"  l_0           : {self.l_0:.0f} mm",
            f"  d (effective) : {self.d:.1f} mm",
            f"  fck / fyk     : {self.fck} / {self.fyk} N/mm²",
            f"  fcd / fyd     : {self.fcd:.2f} / {self.fyd:.2f} N/mm²",
            f"  As_min_v      : {self.As_min_v:.1f} mm²/m",
            f"  As_max_v      : {self.As_max_v:.1f} mm²/m",
            f"  As_min_h      : {self.As_min_h:.1f} mm²/m (minimum absolute)",
        ]
        return "\n".join(lines)

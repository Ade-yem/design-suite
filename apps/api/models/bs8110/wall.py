"""
Wall Section Model
==================
BS 8110-1:1997 – Clause 3.9: Reinforced Concrete Walls

Provides the ``WallSection`` dataclass representing a 1 m wide strip of a
reinforced concrete wall for design under:

  * Axial compression (N) — stocky or slender (Cl 3.9.3)
  * Combined axial + bending (eccentricity > 0.05h  → column strip design)
  * In-plane horizontal shear (Cl 3.9.3.8)

Geometry
--------
  * ``h``   — wall thickness (mm).  The structural dimension resisting
    buckling.  Minimum 75 mm for RC walls per Cl 3.9.1.2.
  * ``l_w`` — wall horizontal length (mm).  Used for shear and detailing.
  * ``l_e`` — effective height of the wall (mm) per Cl 3.9.3.1:
               - Braced wall:   l_e = 0.75 × clear height  (conservatively)
               - Unbraced wall: l_e = 1.0 × clear height  (minimum)
    The caller is responsible for applying the appropriate factor to the
    clear height before passing ``l_e``.

Slenderness classification  (Cl 3.9.3.1)
-----------------------------------------
  * **Stocky** : le/h ≤ 15   (braced)  or  le/h ≤ 10  (unbraced)
  * **Slender** : le/h > limit  →  additional moments must be designed for.

Note: BS 8110 Cl 3.9.1.1 sets the slenderness limit at le/h ≤ 40 for
braced walls (absolute maximum).  However, walls with le/h > 15 (braced)
require additional moment design per Cl 3.9.3.5.

Reinforcement limits  (BS 8110 Table 3.25 / Cl 3.12.5 / Cl 3.12.7)
---------------------------------------------------------------------
The minimum reinforcement depends on steel grade:

  **Vertical steel** (Cl 3.12.5.3 / Table 3.25):
    * fy ≥ 460 N/mm²:  0.25% of bh  each face  (both faces total 0.40%)
    * fy ≤ 250 N/mm²:  0.30% of bh  each face  (both faces total 0.60%)

  **Horizontal steel** (Cl 3.12.7.4):
    * fy ≥ 460 N/mm²:  0.25% of bh  per horizontal layer
    * fy ≤ 250 N/mm²:  0.30% of bh  per horizontal layer

  The design code uses ``As_min_v`` and ``As_min_h`` as the total
  per-metre values on both faces combined.

  Maximum steel (Cl 3.12.6.1): 4% of bh (wall, not a column).

Parameters
----------
h       : Wall thickness (mm). Minimum 75 mm (Cl 3.9.1.2).
l_w     : Horizontal length of the wall panel (mm).
l_e     : Effective height (mm) — caller applies le/h factor.
fcu     : Characteristic cube concrete strength (N/mm²).
fy      : Characteristic main steel yield strength (N/mm²).
cover   : Nominal cover to face of *vertical* bars (mm).
bar_dia : Assumed main vertical bar diameter (mm). Default 12 mm.
braced  : True if the wall is in a braced structure (Cl 3.9.3.1).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WallSection:
    """
    Represents a 1 m wide strip of a reinforced concrete wall.

    All reinforcement areas are expressed per unit horizontal length (mm²/m).
    """

    h: float            # Wall thickness (mm)
    l_w: float          # Horizontal wall length — full panel (mm)
    l_e: float          # Effective height (mm)  — caller applies le factor
    fcu: float          # Characteristic cube strength (N/mm²)
    fy: float           # Steel yield strength (N/mm²)
    cover: float        # Cover to face of vertical bars (mm)
    bar_dia: float = 12.0   # Assumed main vertical bar diameter (mm)
    braced: bool = True

    # ---- derived ----
    d: float = field(init=False)          # Effective depth for flexure (mm)
    As_min_v: float = field(init=False)   # Min vertical steel total both faces (mm²/m)
    As_max_v: float = field(init=False)   # Max vertical steel (mm²/m)
    As_min_h: float = field(init=False)   # Min horizontal steel (mm²/m)

    def __post_init__(self):
        # Effective depth — cover to centroid of tension bar (outer face)
        self.d = self.h - self.cover - self.bar_dia / 2.0

        # ---- Minimum reinforcement (Table 3.25) ----
        # Vertical: both-face total
        if self.fy >= 460:
            self.As_min_v = 0.0025 * 1000.0 * self.h   # 0.25% per face × 2 faces = 0.50% total
        else:
            self.As_min_v = 0.0040 * 1000.0 * self.h   # 0.40% per face × 2 faces = 0.80% total (mild steel)

        # Horizontal (Cl 3.12.7.4) — one layer per face, expressed as total
        if self.fy >= 460:
            self.As_min_h = 0.0025 * 1000.0 * self.h   # 0.25% bh
        else:
            self.As_min_h = 0.0030 * 1000.0 * self.h   # 0.30% bh

        # Maximum vertical steel (Cl 3.12.6.1 for walls, not columns)
        self.As_max_v = 0.04 * 1000.0 * self.h

        self._validate()

    def _validate(self):
        errors = []
        if self.h < 75.0:
            errors.append(f"Wall thickness h ({self.h} mm) < 75 mm minimum (Cl 3.9.1.2).")
        if self.d <= 0:
            errors.append(
                f"Effective depth d = {self.d:.1f} mm ≤ 0. "
                "Increase h or reduce cover/bar_dia."
            )
        if self.l_e <= 0 or self.l_w <= 0:
            errors.append("l_e and l_w must be positive.")
        slenderness = self.l_e / self.h
        abs_limit = 40.0  # Cl 3.9.1.1 absolute maximum for braced wall
        if slenderness > abs_limit:
            errors.append(
                f"Slenderness le/h = {slenderness:.1f} > {abs_limit:.0f} "
                "— exceeds absolute BS 8110 limit (Cl 3.9.1.1)."
            )
        if errors:
            raise ValueError("WallSection validation errors:\n  " + "\n  ".join(errors))

    def summary(self) -> str:
        slender_ratio = self.l_e / self.h
        limit = 15 if self.braced else 10
        classification = "Slender" if slender_ratio > limit else "Stocky"
        lines = [
            f"WallSection ({'Braced' if self.braced else 'Unbraced'}, {classification})",
            f"  h × l_w          : {self.h} × {self.l_w:.0f} mm",
            f"  Effective height  : l_e = {self.l_e:.0f} mm",
            f"  Slenderness le/h  : {slender_ratio:.1f}  (limit {limit}) → {classification}",
            f"  Cover / bar_dia   : {self.cover} / {self.bar_dia} mm",
            f"  d (effective)     : {self.d:.1f} mm",
            f"  fcu / fy          : {self.fcu} / {self.fy} N/mm²",
            f"  As_min_v (both faces): {self.As_min_v:.1f} mm²/m",
            f"  As_min_h         : {self.As_min_h:.1f} mm²/m",
            f"  As_max_v         : {self.As_max_v:.1f} mm²/m",
        ]
        return "\n".join(lines)
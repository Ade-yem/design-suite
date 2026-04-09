"""
EC2 Column Section Model
========================
BS EN 1992-1-1:2004 — Rectangular or circular column geometry and material model.

EC2 divides columns into **short** and **slender** (Cl 5.8.2):

  * A column is slender if the slenderness ratio λ exceeds the limiting value
    λ_lim (Cl 5.8.3.1).
  * For stocky columns (λ ≤ λ_lim), second-order effects may be ignored.
  * For slender columns, second-order moments must be included using one of
    three EC2 methods:
      - **Nominal Stiffness** (Cl 5.8.7)
      - **Nominal Curvature** (Cl 5.8.8) ← used here (simplified, widely used in UK)
      - Non-linear analysis

Geometry conventions
--------------------
  * ``h``  — dimension in the direction of major-axis bending (x-axis).
  * ``b``  — dimension in the direction of minor-axis bending (y-axis).
  * ``l_0x``, ``l_0y`` — effective buckling lengths in each direction (mm).
    Calculated by the caller: l_0 = factor × clear height.
    EC2 Cl 5.8.3.2 Table 5.1 gives effective-length factors.

Reinforcement limits  (EC2 Cl 9.5.2)
--------------------------------------
  * As_min = max(0.10 × N_Ed / fyd,  0.002 × Ac)   — Cl 9.5.2(2)
    Note: As_min depends on N_Ed; the model stores the geometric minimum
    0.002·Ac.  The service overrides this with the N_Ed-dependent value.
  * As_max = 0.04 × Ac   — Cl 9.5.2(3)  [outside laps]
            = 0.08 × Ac  at lap sections

Slenderness  (EC2 Cl 5.8.3)
-----------------------------
  Slenderness ratio: λ = l_0 / i   where i = radius of gyration = √(I/A)
  For a rectangular section:  i_x = h/√12,  i_y = b/√12

  Limiting slenderness:
    λ_lim = 20 · A · B · C / √n
    A = 1/(1 + 0.2φ_ef)   (effective creep ratio; use A=0.7 if φ_ef unknown)
    B = √(1 + 2ω)         (ω = As·fyd/(Ac·fcd); use B=1.1 if ω unknown)
    C = 1.7 − r_m          (r_m = M_01/M_02 moment ratio; use C=0.7 if unknown)
    n = N_Ed/(Ac·fcd)       (relative axial force)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


GAMMA_C: float = 1.50
GAMMA_S: float = 1.15
ALPHA_CC: float = 0.85   # UK NA


@dataclass
class EC2ColumnSection:
    """
    Rectangular RC column cross-section for EC2 design.

    Parameters
    ----------
    b        : Width — dimension in y (minor-axis) direction (mm).
    h        : Depth — dimension in x (major-axis) direction (mm).
    l_0x     : Effective buckling length in x-direction (mm).
    l_0y     : Effective buckling length in y-direction (mm).
    cover    : Nominal cover to face of links (mm).
    fck      : Characteristic cylinder concrete strength (N/mm²).
    fyk      : Characteristic steel yield strength (N/mm²).
    link_dia : Link bar diameter (mm). Default 8.
    bar_dia  : Assumed main bar diameter (used for d/d'). Default 16.
    braced   : True if structure is braced (sway prevented). Default True.

    Derived
    -------
    fcd      : Design concrete strength = α_cc × fck / γ_c.
    fyd      : Design steel strength = fyk / γ_s.
    d        : Effective depth (= h − cover − link_dia − bar_dia/2).
    d_prime  : Depth to compression steel centroid (= cover + link_dia + bar_dia/2).
    i_x, i_y : Radii of gyration (mm).
    lambda_x, lambda_y : Slenderness ratios.
    Ac       : Gross concrete area (mm²).
    As_min_geo : Geometric As_min = 0.002 × Ac (mm²).
    As_max   : Maximum steel area = 0.04 × Ac (mm²).
    """

    b: float
    h: float
    l_0x: float
    l_0y: float
    cover: float
    fck: float
    fyk: float = 500.0
    link_dia: float = 8.0
    bar_dia: float = 16.0
    braced: bool = True

    # Derived
    fcd: float = field(init=False)
    fyd: float = field(init=False)
    fctm: float = field(init=False)
    d: float = field(init=False)
    d_prime: float = field(init=False)
    i_x: float = field(init=False)
    i_y: float = field(init=False)
    lambda_x: float = field(init=False)
    lambda_y: float = field(init=False)
    Ac: float = field(init=False)
    As_min_geo: float = field(init=False)
    As_max: float = field(init=False)

    def __post_init__(self):
        self.fcd  = ALPHA_CC * self.fck / GAMMA_C
        self.fyd  = self.fyk / GAMMA_S

        # fctm for As_min expression (Table 3.1)
        if self.fck <= 50:
            self.fctm = 0.30 * self.fck ** (2.0 / 3.0)
        else:
            self.fctm = 2.12 * math.log(1.0 + (self.fck + 8.0) / 10.0)

        # Effective depths
        self.d       = self.h - self.cover - self.link_dia - self.bar_dia / 2.0
        self.d_prime = self.cover + self.link_dia + self.bar_dia / 2.0

        # Gross area
        self.Ac = self.b * self.h

        # Radii of gyration  i = h/√12  (rectangle)
        self.i_x = self.h / math.sqrt(12.0)
        self.i_y = self.b / math.sqrt(12.0)

        # Slenderness ratios
        self.lambda_x = self.l_0x / self.i_x
        self.lambda_y = self.l_0y / self.i_y

        # Reinforcement limits (Cl 9.5.2)  — geometric minimum
        self.As_min_geo = 0.002 * self.Ac     # Cl 9.5.2(2) lower bound
        self.As_max     = 0.04 * self.Ac      # Cl 9.5.2(3) — outside laps

        self._validate()

    def _validate(self):
        errors = []
        if self.d <= 0:
            errors.append(
                f"Effective depth d = {self.d:.1f} mm ≤ 0. "
                "Increase h or reduce cover/bar_dia."
            )
        if self.fck < 12 or self.fck > 90:
            errors.append(f"fck = {self.fck} N/mm² outside EC2 range [12, 90].")
        if self.l_0x <= 0 or self.l_0y <= 0:
            errors.append("Effective lengths l_0x and l_0y must be positive.")
        if min(self.b, self.h) < 150:
            errors.append(
                f"Minimum column dimension ({min(self.b, self.h)} mm) < 150 mm — "
                "not recommended for practical construction."
            )
        if errors:
            raise ValueError("EC2ColumnSection errors:\n  " + "\n  ".join(errors))

    def lambda_lim(self, n: float,
                   phi_ef: float = 0.0,
                   omega: float = 0.0,
                   r_m: float = 1.0) -> float:
        """
        Limiting slenderness λ_lim  (EC2 Cl 5.8.3.1 Eq. 5.13N).

            λ_lim = 20 · A · B · C / √n

        Parameters
        ----------
        n     : Relative axial force = N_Ed / (Ac · fcd).
        phi_ef: Effective creep ratio φ_ef. Use 0 to get A=0.7 (unknown φ_ef).
        omega : Mechanical reinforcement ratio As·fyd/(Ac·fcd). Use 0 → B=1.1.
        r_m   : Moment ratio M_01/M_02 (ratio of end moments, |r_m| ≤ 1).
                Use 1.0 → C = 0.7 (conservative for symmetric single curvature).

        Returns
        -------
        λ_lim : float
        """
        A = 1.0 / (1.0 + 0.2 * phi_ef) if phi_ef > 0 else 0.7
        B = math.sqrt(1.0 + 2.0 * omega) if omega > 0 else 1.1
        C = 1.7 - r_m   # r_m = M_01/M_02 where M_01 ≤ M_02
        C = max(C, 0.7)  # minimum C when r_m = 1.0 (single curvature)
        n = max(n, 0.01)
        return 20.0 * A * B * C / math.sqrt(n)

    def summary(self) -> str:
        lines = [
            f"EC2ColumnSection ({'Braced' if self.braced else 'Unbraced'})",
            f"  b × h            : {self.b} × {self.h} mm",
            f"  l_0x / l_0y      : {self.l_0x:.0f} / {self.l_0y:.0f} mm",
            f"  λ_x / λ_y        : {self.lambda_x:.1f} / {self.lambda_y:.1f}",
            f"  Cover / bar_dia  : {self.cover} / {self.bar_dia} mm",
            f"  d / d'           : {self.d:.1f} / {self.d_prime:.1f} mm",
            f"  fck / fyk        : {self.fck} / {self.fyk} N/mm²",
            f"  fcd / fyd        : {self.fcd:.2f} / {self.fyd:.2f} N/mm²",
            f"  Ac               : {self.Ac:.0f} mm²",
            f"  As_min_geo       : {self.As_min_geo:.1f} mm²  (0.2% Ac, Cl 9.5.2)",
            f"  As_max           : {self.As_max:.1f} mm²  (4% Ac, Cl 9.5.2)",
        ]
        return "\n".join(lines)

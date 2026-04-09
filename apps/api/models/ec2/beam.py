"""
Eurocode 2 Beam Section Model
==============================
BS EN 1992-1-1:2004 (EC2) — Beam cross-section geometry and material model.

This model mirrors the BS 8110 ``BeamSection`` in structure but uses the
EC2 material partial factors and nomenclature:

  * ``fck`` — characteristic *cylinder* compressive strength (N/mm²).
              EC2 uses cylinder strength throughout; cube strength fck,cube
              is related by fck ≈ 0.8 × fck,cube  (Annex L).
  * ``fyk`` — characteristic reinforcement yield strength (N/mm²). Default 500.
  * ``fywk`` — characteristic yield strength of shear links (N/mm²).
  * γ_c = 1.5  (concrete partial factor, persistent/transient — Cl 2.4.2.4 Table 2.1N)
  * γ_s = 1.15 (steel partial factor, persistent/transient)

Effective depth (Cl 9.2.1)
---------------------------
    d = h − c_nom − φ_link − φ_bar / 2

where c_nom is the nominal cover to the *face* of the link.
EC2 Cl 4.4.1 governs nominal cover; Cl 9.2.1(1) requires adequate
effective depth for lever arm calculations.

Reinforcement limits (EC2 Cl 9.2.1.1)
---------------------------------------
  * Minimum tension steel:
      As_min = max(0.26 × fctm/fyk × b_t × d,  0.0013 × b_t × d)
    where fctm = 0.30 × fck^(2/3) for fck ≤ C50/60  (Table 3.1).
    b_t is the mean width of the tension zone.

  * Maximum steel (tension or compression in any section):
      As_max = 0.04 × A_c  (Cl 9.2.1.1(3))

Redistribution (Cl 5.5)
------------------------
``delta`` is the ratio of redistributed to elastic moment.
For ductility Class B reinforcement and fck ≤ 50:
    x/d ≤ (delta − 0.4)   →   K_lim = delta − 0.4 − (delta−0.4)²/2·η·λ
EC2 simplified: K_lim ≈ 0.60δ − 0.18δ² − 0.21  for ≤ C50 (from SCI guide).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# EC2 material partial safety factors
# ---------------------------------------------------------------------------
GAMMA_C: float = 1.50   # Concrete — persistent / transient  (Table 2.1N)
GAMMA_S: float = 1.15   # Reinforcement  (Table 2.1N)


@dataclass
class EC2BeamSection:
    """
    Cross-section model for EC2 rectangular or flanged beam design.

    Parameters
    ----------
    b       : Web (bending) width (mm).
    h       : Overall section depth (mm).
    cover   : Nominal cover to face of *links* c_nom (mm). (EC2 Cl 4.4.1)
    fck     : Characteristic concrete cylinder strength (N/mm²).
              For C30/37: fck = 30.  See EC2 Table 3.1.
    fyk     : Characteristic reinforcement yield strength (N/mm²). Default 500.
    fywk    : Characteristic shear-link yield strength (N/mm²). Default 500.
    link_dia: Shear link diameter (mm). Default 8 mm.
    bar_dia : Assumed tension bar diameter for d calculation (mm). Default 20.
    comp_bar_dia : Assumed compression bar diameter for d' calculation (mm).
    section_type : ``"rectangular"`` or ``"flanged"``.
    support_condition : ``"simple"``, ``"continuous"``, or ``"cantilever"``.
    bf      : Total effective flange width (mm). Required for flanged beams.
              Determined from EC2 Cl 5.3.2.1 (ledger stiffness formula) by caller.
    hf      : Flange thickness (mm). Required for flanged beams.
    delta   : Moment redistribution ratio (≥ 0.70 for Class B fyk=500 and fck ≤ C50).
              δ = M_redistributed / M_elastic.  Default 1.0 (no redistribution).

    Derived Attributes  (computed in __post_init__)
    -------------------------------------------------
    fcd     : Design concrete cylinder strength = fck / γ_c  (N/mm²).
    fyd     : Design steel yield strength = fyk / γ_s  (N/mm²).
    fywd    : Design link yield strength = fywk / γ_s  (N/mm²).
    fctm    : Mean concrete tensile strength (N/mm²)  — Table 3.1.
    d       : Effective depth (mm).
    d_prime : Compression steel centroid depth (mm).
    K_lim   : Limiting K factor for singly-reinforced design — from δ.
    As_min  : Minimum tension steel (mm²)  — Cl 9.2.1.1.
    As_max  : Maximum steel (mm²)  — Cl 9.2.1.1(3).
    """

    # ---- inputs ----
    b: float
    h: float
    cover: float
    fck: float
    fyk: float = 500.0
    fywk: float = 500.0
    link_dia: float = 8.0
    bar_dia: float = 20.0
    comp_bar_dia: float = 16.0
    section_type: str = "rectangular"
    support_condition: str = "simple"
    bf: Optional[float] = None      # Effective flange width (mm)
    hf: Optional[float] = None      # Flange thickness (mm)
    delta: float = 1.0              # Moment redistribution ratio

    # ---- derived ----
    fcd: float = field(init=False)
    fyd: float = field(init=False)
    fywd: float = field(init=False)
    fctm: float = field(init=False)
    d: float = field(init=False)
    d_prime: float = field(init=False)
    K_lim: float = field(init=False)
    As_min: float = field(init=False)
    As_min_web: float = field(init=False)  # min for web width only (flanged)
    As_max: float = field(init=False)

    def __post_init__(self):
        # ---- Design strengths ----
        self.fcd  = self.fck / GAMMA_C
        self.fyd  = self.fyk / GAMMA_S
        self.fywd = self.fywk / GAMMA_S

        # ---- Mean tensile strength fctm  (Table 3.1) ----
        if self.fck <= 50:
            self.fctm = 0.30 * (self.fck ** (2.0 / 3.0))
        else:
            self.fctm = 2.12 * math.log(1.0 + (self.fck + 8.0) / 10.0)

        # ---- Effective depths ----
        self.d       = self.h - self.cover - self.link_dia - self.bar_dia / 2.0
        self.d_prime = self.cover + self.link_dia + self.comp_bar_dia / 2.0

        # ---- K_lim from moment redistribution δ (Cl 5.5) ----
        # For Class B / C bars and fck ≤ 50:
        #   xu/d ≤ δ − 0.44   (λ = 0.8, η = 1.0)
        # Using the parabolic-rectangular stress block:
        #   K_lim = (δ−0.44)(1 − (δ−0.44)/2) × (η·fcd)/(fck) × 0.8
        # Simplified (SCI P300 approach for fck ≤ 50):
        #   K_lim = 0.60δ − 0.18δ² − 0.21
        #   (minimum 0.167 for δ=1.0)
        self.K_lim = max(0.60 * self.delta - 0.18 * self.delta ** 2 - 0.21, 0.0)
        # Absolute floor per EC2: K_lim ≥ 0 (if δ < 0.7, section always doubly-reinforced)
        # The common simplified limit for simply reinforced:
        # K_lim = 0.167 when δ = 1.0 with rectangular stress block
        if self.delta >= 1.0:
            self.K_lim = 0.167   # Standard singly-reinforced limit

        # ---- Minimum reinforcement (Cl 9.2.1.1) ----
        b_t = self.b   # mean width of tension zone (for rectangular section)
        As_min_formula = 0.26 * (self.fctm / self.fyk) * b_t * self.d
        As_min_lower   = 0.0013 * b_t * self.d
        self.As_min = max(As_min_formula, As_min_lower)

        # For flanged beams, the web controls As_min (tension zone is the web)
        if self.section_type == "flanged" and self.bf is not None:
            self.As_min_web = max(
                0.26 * (self.fctm / self.fyk) * self.b * self.d,
                0.0013 * self.b * self.d,
            )
        else:
            self.As_min_web = self.As_min

        # ---- Maximum reinforcement (Cl 9.2.1.1(3)) ----
        A_c = self.b * self.h
        if self.section_type == "flanged" and self.bf is not None and self.hf is not None:
            A_c = self.b * self.h + (self.bf - self.b) * self.hf
        self.As_max = 0.04 * A_c

        self._validate()

    def _validate(self):
        errors = []
        if self.d <= 0:
            errors.append(
                f"Effective depth d = {self.d:.1f} mm ≤ 0. "
                "Increase h or reduce cover/bar_dia."
            )
        if self.section_type == "flanged":
            if self.bf is None or self.hf is None:
                errors.append("bf and hf must be supplied for flanged sections.")
            elif self.bf < self.b:
                errors.append(f"bf ({self.bf}) < b ({self.b}).")
            elif self.hf >= self.h:
                errors.append(f"hf ({self.hf}) >= h ({self.h}).")
        if not (0.70 <= self.delta <= 1.0):
            errors.append(
                f"delta = {self.delta} outside [0.70, 1.00] (EC2 Cl 5.5 — Class B bars, fck ≤ C50)."
            )
        if self.fck < 12 or self.fck > 90:
            errors.append(f"fck = {self.fck} N/mm² out of EC2 range [12, 90].")
        if errors:
            raise ValueError("EC2BeamSection errors:\n  " + "\n  ".join(errors))

    def summary(self) -> str:
        redist_note = f"δ = {self.delta:.2f}  → K_lim = {self.K_lim:.3f}" if self.delta < 1.0 else ""
        lines = [
            f"EC2BeamSection ({self.section_type}, {self.support_condition})",
            f"  b × h             : {self.b} × {self.h} mm",
            f"  Cover c_nom       : {self.cover} mm",
            f"  Link / bar dia    : H{int(self.link_dia)} / H{int(self.bar_dia)}",
            f"  d  (effective)    : {self.d:.1f} mm",
            f"  d' (comp. bar)    : {self.d_prime:.1f} mm",
            f"  fck / fyk / fywk  : {self.fck} / {self.fyk} / {self.fywk} N/mm²",
            f"  fcd / fyd / fywd  : {self.fcd:.2f} / {self.fyd:.2f} / {self.fywd:.2f} N/mm²",
            f"  fctm              : {self.fctm:.2f} N/mm²",
            f"  As_min / As_max   : {self.As_min:.1f} / {self.As_max:.1f} mm²",
            f"  K_lim             : {self.K_lim:.3f}  (δ = {self.delta})",
        ]
        if self.section_type == "flanged":
            lines += [
                f"  bf (eff. flange)  : {self.bf} mm",
                f"  hf (flange thick) : {self.hf} mm",
            ]
        if redist_note:
            lines.append(f"  Redistribution    : {redist_note}")
        return "\n".join(lines)

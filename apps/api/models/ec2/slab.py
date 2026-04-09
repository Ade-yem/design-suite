"""
EC2 Slab Section Models
========================
BS EN 1992-1-1:2004 — Solid one-way and two-way slab geometry models.

EC2 key differences from BS 8110
----------------------------------
1.  **Concrete strength** uses *cylinder* strength fck (N/mm²), not cube fcu.
2.  **Minimum reinforcement** (Cl 9.3.1.1 references Cl 9.2.1.1):
        As_min = max(0.26·fctm/fyk · b_t · d,   0.0013 · b_t · d)
    where fctm = 0.30·fck^(2/3) for fck ≤ C50/60.
3.  **Maximum reinforcement** (Cl 9.3.1.1(3)):  As_max = 0.04·Ac.
4.  **Deflection** is controlled by span/depth ratio per Cl 7.4.2 (Eq. 7.16),
    not by the BS 8110 Table 3.9 method.
5.  **Two-way slabs** — EC2 uses the exact same yield-line / elastic analysis
    approach.  The Marcus correction to Rankine-Grashof coefficients gives
    reduced moments: m_x = α_sx·n·lx², m_y = α_sy·n·lx².
    Coefficients α_sx and α_sy are tabulated in many national guides
    (e.g. IStructE Manual, Table A3) for ly/lx ratios 1.0–2.0.
6.  **Crack control** — bar spacing limited by EC2 Table 7.3N.
7.  **Shear** — VRd,c from Cl 6.2.2 (same formula as beams).

Two-way slab panel types
-------------------------
``panel_type`` encodes the discontinuous edge configuration:
  ``"SSSS"`` — simply supported all sides
  ``"CSSS"`` — one short edge continuous
  ``"SCSS"`` — two adjacent edges continuous
  ... etc. (full 9-type table used in the service)
Coefficients from IStructE EC2 design guide Table A3.

Layering
--------
In a two-way slab, the short-span (lx) bars are placed in the *outer* layer
(lower d_x) and long-span bars in the *inner* layer (higher d_y):
  d_x = h − cover − bar_dia_x / 2
  d_y = h − cover − bar_dia_x − bar_dia_y / 2
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

GAMMA_C: float = 1.50
GAMMA_S: float = 1.15


@dataclass
class EC2SlabSection:
    """
    1 m wide strip of EC2 solid one-way or two-way slab.

    Parameters
    ----------
    h                : Overall slab thickness (mm).
    cover            : Nominal cover to face of main bars (mm).
    fck              : Characteristic cylinder concrete strength (N/mm²).
    lx               : Shorter span (mm). Used for both one-way and two-way.
    ly               : Longer span (mm). Set equal to lx for one-way slabs.
    fyk              : Characteristic reinforcement yield strength (N/mm²).
    slab_type        : ``"one-way"`` or ``"two-way"``.
    panel_type       : Two-way edge code, e.g. ``"SSSS"``, ``"CSCS"``.
                       Required for two-way slabs.
    support_condition: ``"simple"``, ``"continuous"``, ``"cantilever"``.
    bar_dia_x        : Main bar dia in x (short-span) direction (mm).
    bar_dia_y        : Main bar dia in y (long-span) direction (mm).
    delta            : Moment redistribution ratio. Default 1.0.
    is_end_span      : True if end span of a continuous system (affects L/d K factor).

    Derived
    -------
    fcd, fyd         : Design strengths.
    fctm             : Mean tensile strength (Table 3.1).
    d_x              : Effective depth for short-span bars (outer layer, mm).
    d_y              : Effective depth for long-span bars (inner layer, mm).
    As_min           : Minimum reinforcement per Cl 9.3.1.1 (mm²/m).
    As_max           : Maximum reinforcement = 0.04 × h × 1000 (mm²/m).
    K_lim            : Limiting K for singly-reinforced section.
    """

    h: float
    cover: float
    fck: float
    lx: float
    ly: float
    fyk: float = 500.0
    slab_type: str = "one-way"
    panel_type: Optional[str] = None
    support_condition: str = "simple"
    bar_dia_x: float = 12.0
    bar_dia_y: float = 12.0
    delta: float = 1.0
    is_end_span: bool = False

    # Derived
    fcd:   float = field(init=False)
    fyd:   float = field(init=False)
    fctm:  float = field(init=False)
    d_x:   float = field(init=False)
    d_y:   float = field(init=False)
    K_lim: float = field(init=False)
    As_min: float = field(init=False)
    As_max: float = field(init=False)

    def __post_init__(self):
        self.fcd  = 0.85 * self.fck / GAMMA_C
        self.fyd  = self.fyk / GAMMA_S

        if self.fck <= 50:
            self.fctm = 0.30 * self.fck ** (2.0 / 3.0)
        else:
            self.fctm = 2.12 * math.log(1.0 + (self.fck + 8.0) / 10.0)

        # Effective depths — short-span bars in outer (lower) layer
        self.d_x = self.h - self.cover - self.bar_dia_x / 2.0
        self.d_y = self.h - self.cover - self.bar_dia_x - self.bar_dia_y / 2.0

        # K_lim — simplified EC2 / SCI P300
        self.K_lim = 0.167 if self.delta >= 1.0 else max(
            0.60 * self.delta - 0.18 * self.delta ** 2 - 0.21, 0.0
        )

        # Min reinforcement per m width (Cl 9.3.1.1 → 9.2.1.1)
        b_t = 1000.0
        self.As_min = max(
            0.26 * (self.fctm / self.fyk) * b_t * self.d_x,
            0.0013 * b_t * self.d_x,
        )
        self.As_max = 0.04 * self.h * 1000.0

        self._validate()

    def _validate(self):
        errors = []
        if self.d_x <= 0:
            errors.append(f"d_x = {self.d_x:.1f} mm ≤ 0. Increase h or reduce cover.")
        if self.d_y <= 0:
            errors.append(f"d_y = {self.d_y:.1f} mm ≤ 0. Increase h or reduce cover/bar_dia_x.")
        if self.ly < self.lx:
            errors.append(f"ly ({self.ly}) must be ≥ lx ({self.lx}).")
        if self.slab_type == "two-way" and self.panel_type is None:
            errors.append("panel_type required for two-way slabs.")
        if self.slab_type not in ("one-way", "two-way"):
            errors.append(f"Unknown slab_type '{self.slab_type}'.")
        if not (0.70 <= self.delta <= 1.0):
            errors.append(f"delta = {self.delta} outside [0.70, 1.00].")
        if errors:
            raise ValueError("EC2SlabSection errors:\n  " + "\n  ".join(errors))

    @property
    def ly_lx(self) -> float:
        return self.ly / self.lx

    def summary(self) -> str:
        type_note = self.slab_type
        if self.slab_type == "two-way":
            type_note += f", panel={self.panel_type}, ly/lx={self.ly_lx:.2f}"
        lines = [
            f"EC2SlabSection ({type_note}, {self.support_condition})",
            f"  lx / ly          : {self.lx:.0f} / {self.ly:.0f} mm",
            f"  Thickness h      : {self.h} mm",
            f"  Cover            : {self.cover} mm",
            f"  Bars x / y       : H{int(self.bar_dia_x)} / H{int(self.bar_dia_y)}",
            f"  d_x (outer)      : {self.d_x:.1f} mm",
            f"  d_y (inner)      : {self.d_y:.1f} mm",
            f"  fck / fyk        : {self.fck} / {self.fyk} N/mm²",
            f"  fcd / fyd        : {self.fcd:.2f} / {self.fyd:.2f} N/mm²",
            f"  fctm             : {self.fctm:.2f} N/mm²",
            f"  K_lim            : {self.K_lim:.3f}",
            f"  As_min / As_max  : {self.As_min:.1f} / {self.As_max:.1f} mm²/m",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# EC2 Ribbed / Waffle Slab Section
# ---------------------------------------------------------------------------

@dataclass
class EC2RibbedSection(EC2SlabSection):
    """
    Single rib of a ribbed or waffle slab (EC2 Cl 9.3.3).

    Geometry detailing limits (EC2 Cl 9.3.3)
    -----------------------------------------
      * Rib width ≥ 70 mm  (EC2 Cl 9.3.3(2)).
      * Rib clear spacing ≤ 1500 mm.
      * Topping ≥ 50 mm and ≥ 1/10 of clear rib spacing (Cl 9.3.3(2)).
      * Overall depth ≤ 4× web width.

    Parameters
    ----------
    rib_width        : Web width of each rib b_w (mm). Min 70 mm.
    rib_spacing      : Centre-to-centre rib spacing (mm).
    topping_thickness: Structural topping thickness h_f (mm).
    slab_orientation : ``"one-way"`` or ``"two-way"``.
    """
    rib_width:         float = 120.0
    rib_spacing:       float = 700.0
    topping_thickness: float = 80.0
    slab_orientation:  str   = "one-way"

    # Derived per-rib
    rib_depth:         float = field(init=False)
    clear_rib_spacing: float = field(init=False)
    As_rib_min:        float = field(init=False)
    As_rib_max:        float = field(init=False)

    def __post_init__(self):
        super().__post_init__()
        self.rib_depth         = self.h - self.topping_thickness
        self.clear_rib_spacing = self.rib_spacing - self.rib_width

        # Per-rib min/max — EC2 Cl 9.2.1.1 applied to bw×h
        self.As_rib_min = max(
            0.26 * (self.fctm / self.fyk) * self.rib_width * self.d_x,
            0.0013 * self.rib_width * self.d_x,
        )
        self.As_rib_max = 0.04 * self.rib_width * self.h

        self._validate_rib()

    def _validate_rib(self):
        errors = []
        if self.rib_width < 70.0:
            errors.append(f"rib_width ({self.rib_width} mm) < 70 mm (EC2 Cl 9.3.3(2)).")
        if self.clear_rib_spacing > 1500.0:
            errors.append(f"Clear rib spacing ({self.clear_rib_spacing:.0f} mm) > 1500 mm.")
        min_top = max(50.0, 0.1 * self.clear_rib_spacing)
        if self.topping_thickness < min_top:
            errors.append(
                f"Topping ({self.topping_thickness} mm) < min {min_top:.0f} mm "
                f"[max(50, 0.1×{self.clear_rib_spacing:.0f})] (EC2 Cl 9.3.3(2))."
            )
        if self.h > 4 * self.rib_width:
            errors.append(f"h ({self.h}) > 4×bw ({4*self.rib_width}) mm.")
        if errors:
            raise ValueError("EC2RibbedSection errors:\n  " + "\n  ".join(errors))

    def summary(self) -> str:
        orient = "Waffle (two-way)" if self.slab_orientation == "two-way" else "Ribbed (one-way)"
        lines = [
            f"EC2RibbedSection — {orient}",
            f"  Overall depth h     : {self.h} mm",
            f"  Topping h_f         : {self.topping_thickness} mm",
            f"  Rib depth           : {self.rib_depth:.0f} mm",
            f"  Rib width b_w       : {self.rib_width} mm",
            f"  Rib spacing (c/c)   : {self.rib_spacing} mm",
            f"  Clear spacing       : {self.clear_rib_spacing:.0f} mm",
            f"  Effective depth d_x : {self.d_x:.1f} mm",
            f"  fck / fyk           : {self.fck} / {self.fyk} N/mm²",
            f"  As_rib_min          : {self.As_rib_min:.1f} mm²",
            f"  As_rib_max          : {self.As_rib_max:.1f} mm²",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# EC2 Flat Slab Section
# ---------------------------------------------------------------------------

@dataclass
class EC2FlatSlabSection(EC2SlabSection):
    """
    Flat slab panel supported directly on columns (EC2 Cl 6.4 / 9.4).

    Strip division (Cl 9.4.1)
    --------------------------
    Column strip (CS) width = min(lx/2, ly/2) either side of column line.
    Middle strip (MS) = remainder.

    Punching shear (Cl 6.4.3)
    --------------------------
    Basic control perimeter u_1 is at 2d from the column face.
    For square columns: u_1 = 4c + 2π × 2d = 4c + 4πd.

    Parameters
    ----------
    column_c         : Column dimension (mm) — side for square, dia for circular.
    is_circular_col  : True if circular column.
    is_drop_panel    : Drop panel present.
    drop_thickness_extra : Additional thickness at drop (mm).
    drop_lx, drop_ly : Drop panel extent (mm). Must be ≥ lx/3, ly/3.
    edge_condition   : ``"interior"``, ``"edge"``, or ``"corner"``.
    beta_ec2         : Eccentricity factor β for punching (Cl 6.4.3(3)):
                       1.15 interior, 1.4 edge, 1.5 corner.
    """
    column_c:              float = 400.0
    is_circular_col:       bool  = False
    is_drop_panel:         bool  = False
    drop_thickness_extra:  float = 0.0
    drop_lx:               float = 0.0
    drop_ly:               float = 0.0
    edge_condition:        str   = "interior"
    beta_ec2:              float = field(init=False)

    # Derived
    d_drop:            float = field(init=False)
    col_strip_width:   float = field(init=False)

    _BETA_MAP = {"interior": 1.15, "edge": 1.4, "corner": 1.5}

    def __post_init__(self):
        super().__post_init__()
        self.beta_ec2 = self._BETA_MAP.get(self.edge_condition, 1.15)

        # Effective depth at drop zone
        if self.is_drop_panel and self.drop_thickness_extra > 0:
            self.d_drop = (
                self.h + self.drop_thickness_extra - self.cover - self.bar_dia_x / 2.0
            )
        else:
            self.d_drop = self.d_x

        # Column strip half-width (CS width = min(lx,ly)/2 per Cl 9.4.1, total across panel)
        self.col_strip_width = min(self.lx, self.ly)

        self._validate_flat_ec2()

    def _validate_flat_ec2(self):
        errors = []
        if self.edge_condition not in ("interior", "edge", "corner"):
            errors.append(f"edge_condition must be 'interior', 'edge', or 'corner'.")
        if self.is_drop_panel:
            if self.drop_lx > 0 and self.drop_lx < self.lx / 3.0:
                errors.append(f"drop_lx ({self.drop_lx}) < lx/3 = {self.lx/3:.0f} mm.")
            if self.drop_ly > 0 and self.drop_ly < self.ly / 3.0:
                errors.append(f"drop_ly ({self.drop_ly}) < ly/3 = {self.ly/3:.0f} mm.")
        if errors:
            raise ValueError("EC2FlatSlabSection errors:\n  " + "\n  ".join(errors))

    def summary(self) -> str:
        lines = [
            f"EC2FlatSlabSection — {self.edge_condition.capitalize()} panel",
            f"  Span lx × ly       : {self.lx:.0f} × {self.ly:.0f} mm",
            f"  Thickness h        : {self.h} mm",
            f"  Cover              : {self.cover} mm",
            f"  d_x (short-span)   : {self.d_x:.1f} mm",
            f"  d_drop (at drop)   : {self.d_drop:.1f} mm",
            f"  Column c           : {self.column_c} mm "
            f"({'circular' if self.is_circular_col else 'square'})",
            f"  β (eccentricity)   : {self.beta_ec2}",
            f"  Column strip width : {self.col_strip_width:.0f} mm",
            f"  Drop panel         : {'Yes' if self.is_drop_panel else 'No'}",
            f"  fck / fyk          : {self.fck} / {self.fyk} N/mm²",
            f"  As_min / As_max    : {self.As_min:.1f} / {self.As_max:.1f} mm²/m",
        ]
        return "\n".join(lines)

"""
Slab Section Model
==================
Structured input / derived-geometry object for BS 8110-1:1997 solid slab design.
Supports one-way and two-way spanning solid slabs.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SlabSection:
    """
    Represents a 1m strip of solid slab with properties for calculation.

    For two-way slabs, lx is the *shorter* span and ly the *longer* span.
    The ly/lx ratio drives which coefficient table is used (Table 3.14/3.15).

    Parameters
    ----------
    h              : Overall slab thickness (mm)
    cover          : Nominal concrete cover to main bars (mm)
    fcu            : Characteristic cube strength (N/mm²)
    lx             : Shorter effective span (mm)  — used for both one-way and two-way
    ly             : Longer  effective span (mm)  — two-way only (set equal to lx if one-way)
    fy             : Characteristic steel yield strength (N/mm²)
    slab_type      : "one-way" or "two-way"
    panel_type     : Two-way panel edge condition key (see slab.py TABLE_3_14 for valid keys)
    support_condition : "simple" | "continuous" — governs Table 3.12 and deflection r/d ratio
    beta_b         : Moment redistribution factor (0.7 – 1.0)
    layer          : "outer" (short-span bars) or "inner" (long-span bars) — affects d
    bar_dia        : Assumed main bar diameter (mm)
    bar_dia_outer  : Outer bar diameter when layer="inner" (mm); defaults to bar_dia
    bar_dia_sec    : Secondary / distribution bar diameter (mm)
    """
    h: float
    cover: float
    fcu: float
    lx: float
    ly: float
    fy: float
    slab_type: str = "one-way"
    panel_type: Optional[str] = None        # required for two-way slabs
    support_condition: str = "simple"
    beta_b: float = 1.0
    layer: str = "outer"
    bar_dia: float = 12.0
    bar_dia_outer: float = 0.0
    bar_dia_sec: float = 10.0
    
    # Optional fields for Cl 3.5.2.1 continuity prerequisite checks
    gk: Optional[float] = None
    qk: Optional[float] = None
    num_spans: int = 3
    max_span_ratio: float = 1.0

    b: float = 1000.0   # always 1m strip
    d: float = field(init=False)
    As_min: float = field(init=False)
    As_max: float = field(init=False)

    def __post_init__(self):
        # ---- effective depth -----------------------------------------------
        if self.layer == "outer":
            self.d = self.h - self.cover - (self.bar_dia / 2.0)
        else:
            outer_dia = self.bar_dia_outer if self.bar_dia_outer > 0 else self.bar_dia
            self.d = self.h - self.cover - outer_dia - (self.bar_dia / 2.0)

        # ---- reinforcement limits (Table 3.25) -----------------------------
        min_pct = 0.13 if self.fy >= 460 else 0.24
        self.As_min = (min_pct / 100.0) * self.b * self.h
        self.As_max = 0.04 * self.b * self.h

        self._validate()

    def _validate(self):
        if self.d <= 0:
            raise ValueError(f"Effective depth d = {self.d:.1f} mm ≤ 0. Cover/bar_dia too large.")
        if self.layer not in ("outer", "inner"):
            raise ValueError(f"layer must be 'outer' or 'inner', got '{self.layer}'")
        if not (0.70 <= self.beta_b <= 1.0):
            raise ValueError(f"beta_b = {self.beta_b} outside [0.70, 1.00]")
        if self.slab_type not in ("one-way", "two-way"):
            raise ValueError(f"slab_type must be 'one-way' or 'two-way', got '{self.slab_type}'")
        if self.ly < self.lx:
            raise ValueError(f"ly ({self.ly}) must be ≥ lx ({self.lx}). lx is defined as the shorter span.")
        if self.slab_type == "two-way" and self.panel_type is None:
            raise ValueError("panel_type must be specified for two-way slab design.")

    @property
    def ly_lx(self) -> float:
        return self.ly / self.lx

    def summary(self) -> str:
        type_line = f"{self.slab_type}"
        if self.slab_type == "two-way":
            type_line += f", panel: {self.panel_type}, ly/lx = {self.ly_lx:.2f}"
        lines = [
            f"SlabSection ({type_line}, {self.support_condition}, {self.layer} layer)",
            f"  lx / ly        : {self.lx:.0f} / {self.ly:.0f} mm",
            f"  Thickness h    : {self.h} mm",
            f"  Cover          : {self.cover} mm",
            f"  Main bar dia   : H{int(self.bar_dia)}",
            f"  d  (effective) : {self.d:.1f} mm",
            f"  fcu / fy       : {self.fcu} / {self.fy} N/mm²",
            f"  As,min         : {self.As_min:.1f} mm²/m",
            f"  As,max         : {self.As_max:.1f} mm²/m",
        ]
        return "\n".join(lines)

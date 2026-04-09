"""
Special Slab Section Model
===========================
BS 8110-1:1997 – Ribbed, Waffle, and Flat Slab Geometry Models

This module extends ``SlabSection`` (models/slab.py) with the additional
geometric and material inputs needed for:

  * **Ribbed slabs** (Clause 3.6)  — one-way spanning T-section ribs with a
    structural topping and void formers between ribs.

  * **Waffle slabs** (Clause 3.6)  — two-way ribbed slabs sharing the same
    rib geometry in both directions.

  * **Flat slabs** (Clause 3.7)  — solid slabs supported directly on columns,
    optionally with drop panels or column heads.

Usage
-----
Instantiate ``RibbedWaffleSection`` or ``FlatSlabSection`` as appropriate.
Pass either to ``design_ribbed_slab`` / ``design_flat_slab_*`` in
``services/design/rc/bs8110/special_slab.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from models.slab import SlabSection


# ===========================================================================
# 1. Ribbed / Waffle Slab Section  (BS 8110 Clause 3.6)
# ===========================================================================

@dataclass
class RibbedWaffleSection(SlabSection):
    """
    Represents a single rib of a ribbed or waffle slab.

    Geometry (BS 8110 Cl 3.6.1)
    ----------------------------
    The structural section is a **T-beam** per rib, where:

      * ``rib_width``        (b_w)  — web width of each rib (mm).  Minimum 65 mm.
      * ``rib_spacing``      (b_r)  — centre-to-centre distance between ribs (mm).
                                     Governs the effective flange width (= b_r).
      * ``topping_thickness``(h_f)  — structural topping / flange thickness (mm).
                                     The void-former depth is (h − h_f − ribs go below).
      * ``rib_depth``              — total overall depth h (mm), shared with parent ``h``.

    The parent ``SlabSection`` field ``b`` is **overridden** to equal the
    effective *flange* width (= rib_spacing) for flexural calculations.
    The parent ``d`` is adjusted to account for the bar position inside the rib.

    Detailing Limits (Cl 3.6.1)
    ---------------------------
      * Rib width ≥ 65 mm.
      * Rib clear spacing ≤ 1500 mm.
      * Topping ≥ max(30 mm, 0.1 × clear spacing).
      * Overall depth ≤ 4 × breadth (rib_width).

    Parameters
    ----------
    rib_width          : Width of rib web b_w (mm). Min 65 mm.
    rib_spacing        : Centre-to-centre rib spacing (mm). Max 1500+65 mm for clear ≤ 1500.
    topping_thickness  : Structural topping thickness h_f (mm).
    slab_orientation   : ``"one-way"`` (ribbed) or ``"two-way"`` (waffle).
    """

    # Ribbed / waffle geometry
    rib_width: float = 125.0           # b_w (mm) — minimum 65 mm per Cl 3.6.1.1
    rib_spacing: float = 700.0         # c/c rib spacing (mm)
    topping_thickness: float = 75.0    # h_f (mm) — structural topping / flange thickness
    slab_orientation: str = "one-way"  # "one-way" = ribbed | "two-way" = waffle

    # Derived geometry set in __post_init__
    rib_depth: float = field(init=False)        # Total rib depth below topping (mm)
    clear_rib_spacing: float = field(init=False) # Clear gap between ribs (mm)
    As_rib_min: float = field(init=False)        # Min steel per *rib* (mm²)
    As_rib_max: float = field(init=False)        # Max steel per *rib* (mm²)

    def __post_init__(self):
        # Run parent first (sets b=1000, d, As_min/max on 1m strip basis)
        super().__post_init__()

        # -- Override effective width for T-section flexural calculation --
        # Cl 3.6.1.5: effective flange width = rib spacing (the full topping between ribs)
        self.b = self.rib_spacing

        # -- Recalculate effective depth inside the rib (same bar position) --
        # d = h - cover - bar_dia/2  (unchanged from parent, but now meaningful as rib d)

        # -- Rib-level geometry --
        self.rib_depth = self.h - self.topping_thickness
        self.clear_rib_spacing = self.rib_spacing - self.rib_width

        # -- Min/Max reinforcement *per rib* (not per 1m) --
        # Table 3.25: min 0.13% of (bw × h) for fy ≥ 460
        min_pct = 0.13 if self.fy >= 460 else 0.24
        self.As_rib_min = (min_pct / 100.0) * self.rib_width * self.h
        self.As_rib_max = 0.04 * self.rib_width * self.h

        # Override parent As_min/max with per-rib values for design use
        self.As_min = self.As_rib_min
        self.As_max = self.As_rib_max

        self._validate_ribbed()

    def _validate_ribbed(self):
        """Enforce BS 8110 Cl 3.6.1 geometric detailing limits."""
        errors = []
        if self.rib_width < 65.0:
            errors.append(f"rib_width ({self.rib_width} mm) < 65 mm minimum (Cl 3.6.1.1).")
        if self.clear_rib_spacing > 1500.0:
            errors.append(
                f"Clear rib spacing ({self.clear_rib_spacing:.0f} mm) > 1500 mm limit (Cl 3.6.1.2)."
            )
        min_topping = max(30.0, 0.1 * self.clear_rib_spacing)
        if self.topping_thickness < min_topping:
            errors.append(
                f"Topping thickness ({self.topping_thickness} mm) < required "
                f"{min_topping:.0f} mm [max(30, 0.1×clear)] (Cl 3.6.1.3)."
            )
        if self.h > 4.0 * self.rib_width:
            errors.append(
                f"Overall depth h ({self.h} mm) > 4 × rib_width ({4*self.rib_width:.0f} mm) (Cl 3.6.1.4)."
            )
        if errors:
            raise ValueError("RibbedWaffleSection geometry violations:\n  " + "\n  ".join(errors))

    def summary(self) -> str:
        """Return a human-readable summary of the rib geometry for design notes."""
        orient = "Waffle (two-way)" if self.slab_orientation == "two-way" else "Ribbed (one-way)"
        lines = [
            f"RibbedWaffleSection — {orient} ({self.support_condition})",
            f"  Span lx / ly      : {self.lx:.0f} / {self.ly:.0f} mm",
            f"  Overall depth h   : {self.h} mm",
            f"  Topping h_f       : {self.topping_thickness} mm",
            f"  Rib depth below topping: {self.rib_depth:.0f} mm",
            f"  Rib width b_w     : {self.rib_width} mm",
            f"  Rib spacing b_r   : {self.rib_spacing} mm (c/c)",
            f"  Clear rib spacing : {self.clear_rib_spacing:.0f} mm",
            f"  Cover             : {self.cover} mm",
            f"  d (effective)     : {self.d:.1f} mm",
            f"  fcu / fy          : {self.fcu} / {self.fy} N/mm²",
            f"  As_min per rib    : {self.As_rib_min:.1f} mm²",
            f"  As_max per rib    : {self.As_rib_max:.1f} mm²",
        ]
        return "\n".join(lines)


# ===========================================================================
# 2. Flat Slab Section  (BS 8110 Clause 3.7)
# ===========================================================================

@dataclass
class FlatSlabSection(SlabSection):
    """
    Represents a flat slab panel supported directly on columns.

    Geometry (BS 8110 Cl 3.7)
    -------------------------
    A flat slab spans in two directions between columns.  The design divides
    the panel width into:

      * **Column Strip (CS)** — width = min(0.5×L_x, 0.5×L_y) either side of
        column centreline (Cl 3.7.2.1).
      * **Middle Strip (MS)** — the remainder of the panel width.

    Drop panels (Cl 3.7.1.5)
    -------------------------
    A drop panel must project at least h/6 below the soffit and extend at
    least L/3 in each direction from the column centreline.  When present,
    the effective depth for punching shear calculations increases.

    Column Heads (Cl 3.7.1.4)
    -------------------------
    An effective column head dimension ``hc`` is computed per Cl 3.7.1.4
    as the lesser of:
      * Actual head diameter (or effective side for non-circular).
      * ``l_c + 2 × (head depth)`` limited to 0.25 × L_c (panel dimension).

    Parameters
    ----------
    column_dia      : Column dimension (mm).  For circular columns, this is
                      the actual diameter; for square, the side length.
                      This is l_c in the code.
    is_circular_col : True if the column is circular (affects perimeter).
                      Default False (square column assumed).
    is_drop_panel   : True if drop panels are present (Cl 3.7.1.5).
    drop_thickness  : Additional thickness below soffit at drop panel (mm).
    drop_lx         : Drop panel extent in lx direction (mm). Must be ≥ lx/3.
    drop_ly         : Drop panel extent in ly direction (mm). Must be ≥ ly/3.
    edge_condition  : Panel position: ``"interior"``, ``"edge"``, or ``"corner"``.
    """

    column_dia: float = 400.0           # l_c — column dimension (diameter or side, mm)
    is_circular_col: bool = False       # True = circular column
    is_drop_panel: bool = False         # Drop panel present?
    drop_thickness: float = 0.0         # Extra depth at drop (mm)
    drop_lx: float = 0.0               # Drop extent in lx direction (mm)
    drop_ly: float = 0.0               # Drop extent in ly direction (mm)
    edge_condition: str = "interior"   # "interior" | "edge" | "corner"

    # Derived
    hc: float = field(init=False)       # Effective column head (mm) per Cl 3.7.1.4
    d_drop: float = field(init=False)   # Effective depth at drop zone (mm)
    col_strip_width: float = field(init=False)  # Column strip half-width (mm)

    def __post_init__(self):
        super().__post_init__()

        # Effective column head hc (Cl 3.7.1.4)
        # Simplified: for columns without heads use column_dia directly.
        # The code full formula requires head geometry; we use column_dia as hc.
        self.hc = self.column_dia

        # Effective depth at drop panel zone
        if self.is_drop_panel and self.drop_thickness > 0:
            self.d_drop = self.h + self.drop_thickness - self.cover - (self.bar_dia / 2.0)
        else:
            self.d_drop = self.d

        # Column strip width = min(0.5 lx, 0.5 ly) either side, total = min(lx, ly)
        self.col_strip_width = min(self.lx, self.ly)  # total CS width across panel

        self._validate_flat()

    def _validate_flat(self):
        """Validate flat slab geometry per BS 8110 Cl 3.7."""
        errors = []
        if self.is_drop_panel:
            if self.drop_lx > 0 and self.drop_lx < self.lx / 3.0:
                errors.append(
                    f"Drop panel lx extent ({self.drop_lx} mm) < lx/3 = {self.lx/3:.0f} mm (Cl 3.7.1.5)."
                )
            if self.drop_ly > 0 and self.drop_ly < self.ly / 3.0:
                errors.append(
                    f"Drop panel ly extent ({self.drop_ly} mm) < ly/3 = {self.ly/3:.0f} mm (Cl 3.7.1.5)."
                )
            if self.drop_thickness < self.h / 6.0:
                errors.append(
                    f"Drop thickness ({self.drop_thickness} mm) < h/6 = {self.h/6:.0f} mm (Cl 3.7.1.5). "
                    "Drop must project ≥ h/6 below soffit."
                )
        if self.edge_condition not in ("interior", "edge", "corner"):
            errors.append(
                f"edge_condition must be 'interior', 'edge', or 'corner'; got '{self.edge_condition}'."
            )
        if errors:
            raise ValueError("FlatSlabSection geometry violations:\n  " + "\n  ".join(errors))

    def summary(self) -> str:
        """Return a human-readable summary of the flat slab geometry."""
        drop_str = (
            f"Yes (extra depth {self.drop_thickness} mm, extent {self.drop_lx}×{self.drop_ly} mm)"
            if self.is_drop_panel else "No"
        )
        lines = [
            f"FlatSlabSection — {self.edge_condition.capitalize()} panel ({self.support_condition})",
            f"  Span lx × ly      : {self.lx:.0f} × {self.ly:.0f} mm",
            f"  Slab thickness h  : {self.h} mm",
            f"  Cover             : {self.cover} mm",
            f"  d (slab)          : {self.d:.1f} mm",
            f"  d (drop zone)     : {self.d_drop:.1f} mm",
            f"  Column dim (l_c)  : {self.column_dia} mm  "
            f"({'circular' if self.is_circular_col else 'square'})",
            f"  Effective hc      : {self.hc:.0f} mm (Cl 3.7.1.4)",
            f"  Drop panel        : {drop_str}",
            f"  Column strip width: {self.col_strip_width:.0f} mm",
            f"  fcu / fy          : {self.fcu} / {self.fy} N/mm²",
            f"  As_min / As_max   : {self.As_min:.1f} / {self.As_max:.1f} mm²/m",
        ]
        return "\n".join(lines)
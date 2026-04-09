"""
Foundation Section Models
=========================
BS 8110-1:1997 – Clause 3.11: Foundations

Provides two structured data models for foundation design:

  * **PadFooting** (Cl 3.11.3) — isolated rectangular pad footing
    supporting a single column under combined axial load and moment.

  * **PileCap** (Cl 3.11.4) — pile cap connecting a single column
    to a group of piles.

Geometry conventions
--------------------
For **PadFooting**:
  * ``lx`` — footing dimension parallel to the x-axis (same direction as
    ``column_cx``). Moment in the x-direction spans across ``lx``,
    causing bending over width ``ly``.
  * ``ly`` — footing dimension parallel to the y-axis. Moment in the
    y-direction bends over width ``lx``.
  * ``h`` — overall thickness (mm), measured from top of footing to
    underside of blinding.
  * ``d`` — effective depth (mm) = h − cover − bar_dia/2.
    (Cover is to *face* of bar; d is to *centroid* of tension steel.)

For **PileCap**:
  * All of the above apply, plus pile geometry fields.
  * ``pile_spacing`` — centre-to-centre distance between adjacent piles (mm).
  * ``pile_dia``     — diameter of each pile (mm).
  * ``num_piles``    — total number of piles in the cap.

Detailing note
--------------
The effective depth ``d`` is calculated as ``h - cover - bar_dia/2``
(cover to the *face* of the outermost layer of steel, then half a bar
diameter to the centroid).  This is consistent with BS 8110 Cl 3.11.1
and the same convention used throughout this design suite.

For pile caps with two bar layers, reserve an additional bar diameter
when computing d for the inner layer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FoundationBase:
    """
    Shared geometry and material fields for all foundation types.

    Parameters
    ----------
    lx      : Footing dimension in x-direction (mm). For pad footings with
              uniaxial bending in x, this is the dimension parallel to the
              bending plane. For pile caps, lx is the pile-row spacing in x.
    ly      : Footing dimension in y-direction (mm).
    h       : Overall thickness (depth) of the footing (mm).
    fcu     : Characteristic cube concrete strength (N/mm²).
    fy      : Characteristic reinforcement yield strength (N/mm²).
    cover   : Nominal concrete cover to the *face* of the outermost bar (mm).
              This is cover to links (or to main bars if no links). Minimum
              50 mm for footings cast against blinding (BS 8110 Table 3.4).
    column_cx : Column dimension in x-direction (mm).
    column_cy : Column dimension in y-direction (mm).
    bar_dia : Assumed main bar diameter (mm). Default 16 mm.
    """

    lx: float           # Footing length x (mm)
    ly: float           # Footing length y (mm)
    h: float            # Overall thickness (mm)
    fcu: float          # Concrete cube strength (N/mm²)
    fy: float           # Steel yield strength (N/mm²)
    cover: float        # Nominal cover to face of main bars (mm)
    column_cx: float    # Column size in x (mm)
    column_cy: float    # Column size in y (mm)
    bar_dia: float = 16.0

    # Derived
    d: float = field(init=False)
    As_min: float = field(init=False)
    As_max: float = field(init=False)

    def __post_init__(self):
        # Effective depth: cover to face of bar + half bar diameter to centroid
        # Consistent with BS 8110 Cl 3.11.1 and the rest of the design suite.
        self.d = self.h - self.cover - self.bar_dia / 2.0

        # Reinforcement limits per Table 3.25 (slab-like element in footing)
        # Min 0.13% bh for fy ≥ 460, 0.24% for mild steel — per 1m strip
        min_pct = 0.13 if self.fy >= 460 else 0.24
        # Store as mm²/m for the governing direction (width = 1000 mm)
        self.As_min = (min_pct / 100.0) * 1000.0 * self.h
        self.As_max = 0.04 * 1000.0 * self.h

        self._validate_base()

    def _validate_base(self):
        errors = []
        if self.d <= 0:
            errors.append(
                f"Effective depth d = {self.d:.1f} mm ≤ 0. "
                "Increase h or reduce cover/bar_dia."
            )
        if self.cover < 50.0:
            errors.append(
                f"Cover ({self.cover} mm) < 50 mm minimum for footings cast against blinding "
                "(BS 8110 Table 3.4, Cl 3.3.1). Check exposure condition."
            )
        if self.lx <= 0 or self.ly <= 0 or self.h <= 0:
            errors.append("lx, ly, and h must be positive.")
        if errors:
            raise ValueError("FoundationBase validation errors:\n  " + "\n  ".join(errors))

    def summary(self) -> str:
        raise NotImplementedError("Use PadFooting.summary() or PileCap.summary().")


@dataclass
class PadFooting(FoundationBase):
    """
    Isolated pad footing supporting a single column.

    Design basis (BS 8110 Cl 3.11.2 & 3.11.3)
    ------------------------------------------
    The pad is treated as a **cantilever** in each direction, fixed at the
    column face, under a uniform net upward bearing pressure from the soil.

    The critical sections for design are:
      * **Flexure (Cl 3.11.2.2)**: At the column face (``column_cx/2`` from
        pad centreline in x-direction, ``column_cy/2`` in y-direction).
      * **Beam shear (Cl 3.11.3.3)**: At effective depth ``d`` from the
        column face — i.e. at ``column_cx/2 + d`` from pad centreline.
        (Not at the column face as for beams/slabs.)
      * **Punching shear (Cl 3.11.3.4b)**: At 1.5d from the column face,
        with the perimeter having rounded corners per Cl 3.7.7.3.

    Bearing pressure check is outside this class — the caller must supply
    the net upward pressure or the total design column load.

    Parameters
    ----------
    All parameters inherited from ``FoundationBase``.
    No additional parameters are required for a simple pad footing.

    Notes
    -----
    * For eccentrically loaded pads, the bearing pressure distribution is
      trapezoidal.  The design service accepts N and M and derives the
      critical bearing pressure per unit length.
    * A symmetric pad (lx=ly) under axial load only requires the same
      steel in both directions and one beam shear check.
    """
    pass  # No additional fields — all geometry is in FoundationBase

    def summary(self) -> str:
        lines = [
            "PadFooting",
            f"  Footing plan   : {self.lx:.0f} × {self.ly:.0f} mm",
            f"  Thickness h    : {self.h} mm",
            f"  Cover          : {self.cover} mm",
            f"  d (effective)  : {self.d:.1f} mm",
            f"  Column         : {self.column_cx:.0f} × {self.column_cy:.0f} mm",
            f"  fcu / fy       : {self.fcu} / {self.fy} N/mm²",
            f"  As_min         : {self.As_min:.1f} mm²/m",
            f"  As_max         : {self.As_max:.1f} mm²/m",
        ]
        return "\n".join(lines)


@dataclass
class PileCap(FoundationBase):
    """
    Pile cap connecting a column to a group of driven or bored piles.

    Design basis (BS 8110 Cl 3.11.4)
    ---------------------------------
    Two design methods are recognised by BS 8110:

    1. **Bending theory** (Cl 3.11.4.2) — treated as an inverted flat slab
       loaded upward by pile reactions. Used when pile spacing > 3Φ.
    2. **Truss analogy** (Cl 3.11.4.1) — the tension tie force in the
       horizontal steel is derived from the truss geometry:

           T = N × (pile spacing / 2) / (2 × z)

       where ``z`` is the lever arm from the compression zone in the
       column to the centroid of the tension steel.

    This implementation uses the **truss analogy** for all pile caps
    (conservative and recommended for standard 2-pile to 6-pile caps).

    Shear (Cl 3.11.4.3 / 3.11.4.4)
    --------------------------------
    The critical shear section is at 20% of the pile diameter inside the
    *pile face* (not at d from column face as in beams).  For a 2-pile cap
    the critical section lies at distance ``av`` from the column face:

        av = pile_spacing/2 − 0.3 × pile_dia − column_cx/2

    An enhancement factor ``2d/av`` is applied to vc per Cl 3.4.5.8
    (Cl 3.11.4.4 explicitly references this).  The factor is capped at 2d/av
    where av must be ≥ d/5 to prevent unrealistically large enhancements.

    Punching shear at the column face (Cl 3.11.4.5) must also be checked.

    Parameters
    ----------
    pile_dia      : Pile diameter (mm).
    pile_spacing  : Centre-to-centre pile spacing (mm).
    num_piles     : Number of piles in the cap.
    """

    pile_dia: float = 300.0         # Pile diameter (mm)
    pile_spacing: float = 900.0     # Centre-to-centre pile spacing (mm)
    num_piles: int = 2              # Number of piles

    def __post_init__(self):
        super().__post_init__()
        self._validate_pile_cap()

    def _validate_pile_cap(self):
        errors = []
        if self.pile_spacing < 3.0 * self.pile_dia:
            errors.append(
                f"Pile spacing ({self.pile_spacing} mm) < 3×pile_dia "
                f"({3*self.pile_dia:.0f} mm). Minimum per BS 8110 / good practice."
            )
        if self.num_piles < 2:
            errors.append("num_piles must be ≥ 2.")
        if errors:
            # Warnings only — pile spacing can be waived for driven piles
            import warnings as _w
            for e in errors:
                _w.warn(e)

    def summary(self) -> str:
        lines = [
            "PileCap",
            f"  Cap plan       : {self.lx:.0f} × {self.ly:.0f} mm",
            f"  Thickness h    : {self.h} mm",
            f"  Cover          : {self.cover} mm",
            f"  d (effective)  : {self.d:.1f} mm",
            f"  Column         : {self.column_cx:.0f} × {self.column_cy:.0f} mm",
            f"  Piles          : {self.num_piles} no., Φ = {self.pile_dia:.0f} mm, "
            f"spacing = {self.pile_spacing:.0f} mm c/c",
            f"  fcu / fy       : {self.fcu} / {self.fy} N/mm²",
            f"  As_min         : {self.As_min:.1f} mm²/m",
        ]
        return "\n".join(lines)
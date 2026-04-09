"""
Foundation Section Models
=========================
BS EN 1992-1-1:2004 — Clause 9.8: Foundations

Provides two structured data models for Eurocode 2 (EC2) foundation design:

  * **PadFooting** — isolated rectangular pad footing
    supporting a single column under combined axial load and moment.

  * **PileCap** (Cl 9.8.1) — pile cap connecting a single column
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

For **PileCap**:
  * All of the above apply, plus pile geometry fields.
  * ``pile_spacing`` — centre-to-centre distance between adjacent piles (mm).
  * ``pile_dia``     — diameter of each pile (mm).
  * ``num_piles``    — total number of piles in the cap.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FoundationBase:
    """
    Shared geometry and material fields for EC2 foundation types.
    
    Parameters
    ----------
    lx : float
        Footing length in the x-direction (mm).
    ly : float
        Footing length in the y-direction (mm).
    h : float
        Overall thickness of the footing (mm).
    fck : float
        Characteristic cylinder concrete strength (N/mm2).
    fyk : float, optional
        Characteristic reinforcement yield strength (N/mm2). Default is 500.0.
    cover : float, optional
        Nominal concrete cover to the face of main bars (mm). Default is 50.0.
    column_cx : float, optional
        Column dimension in the x-direction (mm). Default is 400.0.
    column_cy : float, optional
        Column dimension in the y-direction (mm). Default is 400.0.
    bar_dia : float, optional
        Assumed main bar diameter (mm). Default is 16.0.
    """

    lx: float
    ly: float
    h: float
    fck: float
    fyk: float = 500.0
    cover: float = 50.0
    column_cx: float = 400.0
    column_cy: float = 400.0
    bar_dia: float = 16.0

    # Derived
    d: float = field(init=False)
    fctm: float = field(init=False)
    As_min: float = field(init=False)
    As_max: float = field(init=False)

    def __post_init__(self):
        """Calculate derived effective depth and reinforcement limits."""
        self.d = self.h - self.cover - self.bar_dia / 2.0

        if self.fck <= 50:
            self.fctm = 0.30 * self.fck ** (2.0 / 3.0)
        else:
            self.fctm = 2.12 * math.log(1.0 + (self.fck + 8.0) / 10.0)

        # Min reinforcement per m width (Cl 9.3.1.1 -> 9.2.1.1)
        b_t = 1000.0
        self.As_min = max(
            0.26 * (self.fctm / self.fyk) * b_t * self.d,
            0.0013 * b_t * self.d,
        )
        self.As_max = 0.04 * 1000.0 * self.h

        self._validate_base()

    def _validate_base(self):
        """Internal validation for common foundation parameters."""
        errors = []
        if self.d <= 0:
            errors.append(f"Effective depth d = {self.d:.1f} mm <= 0. Increase h or reduce cover.")
        if self.cover < 40.0:
            errors.append(
                f"Cover ({self.cover} mm) is small for footings. "
                "Consider >= 40-50 mm depending on exposure and blinding."
            )
        if self.lx <= 0 or self.ly <= 0 or self.h <= 0:
            errors.append("lx, ly, and h must be positive.")
        if errors:
            raise ValueError("FoundationBase validation errors:\n  " + "\n  ".join(errors))

    def summary(self) -> str:
        """Returns a formatted summary of the foundation model."""
        raise NotImplementedError("Use PadFooting.summary() or PileCap.summary().")


@dataclass
class PadFooting(FoundationBase):
    """
    Isolated pad footing supporting a single column per EC2.
    """
    def summary(self) -> str:
        """Returns a string summary of the pad footing properties."""
        lines = [
            "EC2 PadFooting",
            f"  Footing plan   : {self.lx:.0f} × {self.ly:.0f} mm",
            f"  Thickness h    : {self.h} mm",
            f"  Cover          : {self.cover} mm",
            f"  d (effective)  : {self.d:.1f} mm",
            f"  Column         : {self.column_cx:.0f} × {self.column_cy:.0f} mm",
            f"  fck / fyk      : {self.fck} / {self.fyk} N/mm²",
            f"  As_min         : {self.As_min:.1f} mm²/m",
            f"  As_max         : {self.As_max:.1f} mm²/m",
        ]
        return "\n".join(lines)


@dataclass
class PileCap(FoundationBase):
    """
    Pile cap connecting a column to a group of piles per EC2.
    
    Parameters
    ----------
    All FoundationBase parameters plus:
    pile_dia : float, optional
        Diameter of each pile (mm). Default is 300.0.
    pile_spacing : float, optional
        Centre-to-centre distance between adjacent piles (mm). Default is 900.0.
    num_piles : int, optional
        Total number of piles in the group. Default is 2.
    """
    pile_dia: float = 300.0
    pile_spacing: float = 900.0
    num_piles: int = 2

    def __post_init__(self):
        """Post-init with pile cap specific validation."""
        super().__post_init__()
        self._validate_pile_cap()

    def _validate_pile_cap(self):
        """Internal validation for pile cap specific parameters."""
        errors = []
        if self.num_piles < 2:
            errors.append("num_piles must be >= 2.")
        if errors:
            import warnings as _w
            for e in errors:
                _w.warn(e)

    def summary(self) -> str:
        """Returns a string summary of the pile cap properties."""
        lines = [
            "EC2 PileCap",
            f"  Cap plan       : {self.lx:.0f} × {self.ly:.0f} mm",
            f"  Thickness h    : {self.h} mm",
            f"  Cover          : {self.cover} mm",
            f"  d (effective)  : {self.d:.1f} mm",
            f"  Column         : {self.column_cx:.0f} × {self.column_cy:.0f} mm",
            f"  Piles          : {self.num_piles} no., Φ = {self.pile_dia:.0f} mm, "
            f"spacing = {self.pile_spacing:.0f} mm c/c",
            f"  fck / fyk      : {self.fck} / {self.fyk} N/mm²",
            f"  As_min         : {self.As_min:.1f} mm²/m",
        ]
        return "\n".join(lines)

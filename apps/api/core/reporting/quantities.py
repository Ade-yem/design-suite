"""
Module 3 — Material Quantity Engine
=====================================
Computes concrete, formwork, and reports steel take-off quantities for
all members in a ``ReportDataModel``.

This module **never designs**. All geometric inputs (b, h, L, etc.) are
read directly from the ``geometry`` field on each ``ReportMember``.

Volume and area formulae are applied per member type following standard
engineering conventions. Slab topping and rib geometries are handled for
all specialised slab types.

Classes
-------
MaterialQuantityEngine
    Main entry point. ``build(rdm, rebar_schedule)`` returns the full
    quantities context dict.
MemberQuantities
    Dataclass for one member's concrete, formwork, and steel quantities.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from core.reporting.normalizer import ReportDataModel, ReportMember


# ---------------------------------------------------------------------------
# MemberQuantities
# ---------------------------------------------------------------------------

@dataclass
class MemberQuantities:
    """
    Concrete, formwork, and steel quantities for one structural member.

    Parameters
    ----------
    member_id : str
        Unique member identifier.
    member_type : str
        Structural type ("beam", "column", etc.).
    floor_level : str
        Floor level description.
    concrete_m3 : float
        Concrete volume in cubic metres.
    formwork_m2 : float
        Formwork contact area in square metres.
    steel_kg : float
        Reinforcement steel mass in kilograms (sourced from bar schedule).
    notes : list[str]
        Any quantity assumptions or edge-case notes.
    """

    member_id: str
    member_type: str
    floor_level: str
    concrete_m3: float = 0.0
    formwork_m2: float = 0.0
    steel_kg: float = 0.0
    notes: list = None

    def __post_init__(self):
        if self.notes is None:
            self.notes = []

    def as_dict(self) -> dict:
        """Serialise to a plain dict for template rendering."""
        return {
            "member_id": self.member_id,
            "member_type": self.member_type,
            "floor_level": self.floor_level,
            "concrete_m3": round(self.concrete_m3, 3),
            "formwork_m2": round(self.formwork_m2, 2),
            "steel_kg": round(self.steel_kg, 1),
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Material Quantity Engine
# ---------------------------------------------------------------------------

class MaterialQuantityEngine:
    """
    Module 3: Material Quantity Engine.

    Reads geometry from each ``ReportMember`` and computes:
    * Concrete volume (m³) by member type using standard formulae.
    * Formwork contact area (m²) by member type.
    * Reinforcement steel mass (kg) from the pre-built bar schedule.

    The engine dispatches geometry calculations to member-type-specific
    private methods. All values are reported in SI units (m, m², m³, kg).

    Usage
    -----
    ::

        engine = MaterialQuantityEngine()
        quantities = engine.build(rdm, rebar_schedule)
        # quantities["members"]         → list[dict] per member
        # quantities["summary_by_type"] → dict[type, {concrete, formwork, steel}]
        # quantities["grand_total"]     → {concrete_m3, formwork_m2, steel_kg}
    """

    def build(
        self, rdm: ReportDataModel, rebar_schedule: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Build the material quantities take-off for the entire project.

        Parameters
        ----------
        rdm : ReportDataModel
            The fully normalised report data model.
        rebar_schedule : dict
            Output from ``RebarScheduleEngine.build(rdm)``.
            Used to source steel mass per member from ``by_member``.

        Returns
        -------
        dict with keys:
            members : list[dict]
                Per-member quantities (serialised MemberQuantities).
            summary_by_type : dict[str, dict]
                Quantities aggregated by member type.
                Each value: {concrete_m3, formwork_m2, steel_kg}.
            summary_by_floor : dict[str, dict]
                Quantities aggregated by floor level.
            grand_total : dict
                {concrete_m3, formwork_m2, steel_kg}.
        """
        steel_by_member: dict[str, float] = self._steel_by_member(rebar_schedule)
        member_quantities: list[MemberQuantities] = []

        for member in rdm.members:
            mq = self._compute_member(member, steel_by_member)
            member_quantities.append(mq)

        member_dicts = [mq.as_dict() for mq in member_quantities]

        return {
            "members": member_dicts,
            "summary_by_type": self._group_summary(member_quantities, "member_type"),
            "summary_by_floor": self._group_summary(member_quantities, "floor_level"),
            "grand_total": self._grand_total(member_quantities),
        }

    # ------------------------------------------------------------------ private

    def _compute_member(
        self, member: ReportMember, steel_by_member: dict[str, float]
    ) -> MemberQuantities:
        """Dispatch to type-specific computation method."""
        g = member.geometry
        mt = member.member_type.lower()
        notes: list[str] = []

        dispatch = {
            "beam": self._beam,
            "column": self._column,
            "wall": self._wall,
            "slab_one_way": self._slab_solid,
            "slab_two_way": self._slab_solid,
            "slab_ribbed": self._slab_ribbed,
            "slab_waffle": self._slab_waffle,
            "slab_flat": self._slab_solid,
            "footing_pad": self._footing_pad,
            "footing_pile": self._footing_pad,  # Same formula for cap geometry
            "staircase": self._staircase,
        }

        compute_fn = dispatch.get(mt)
        if compute_fn is None:
            notes.append(f"Unknown member type '{mt}': quantities set to 0.")
            concrete, formwork = 0.0, 0.0
        else:
            concrete, formwork = compute_fn(g, notes)

        steel = steel_by_member.get(member.member_id, 0.0)

        return MemberQuantities(
            member_id=member.member_id,
            member_type=member.member_type,
            floor_level=member.floor_level,
            concrete_m3=concrete,
            formwork_m2=formwork,
            steel_kg=steel,
            notes=notes,
        )

    # ------------------------------------------------------------------ formulae

    @staticmethod
    def _beam(g: dict, notes: list) -> tuple[float, float]:
        """
        Concrete volume and formwork for a rectangular or flanged beam.

        Formulae
        --------
        Concrete : b × h × L (rectangular) or (b×h + (bf−b)×hf) × L (flanged)
        Formwork : (b + 2×hw) × L   (soffit + two exposed sides)
        """
        b = g.get("b", 0) / 1000      # mm → m
        h = g.get("h", 0) / 1000
        L = g.get("span_mm", g.get("length_mm", 0)) / 1000 or g.get("span_m", g.get("length_m", 0))

        bf = g.get("bf", b * 1000) / 1000
        hf = g.get("hf", 0) / 1000
        hw = h - hf  # web height

        if bf > b and hf > 0:
            concrete = (b * hw + bf * hf) * L
            notes.append("Flanged beam: concrete includes flange area.")
        else:
            concrete = b * h * L

        formwork = (b + 2 * h) * L   # soffit + sides (no top)
        return concrete, formwork

    @staticmethod
    def _slab_solid(g: dict, notes: list) -> tuple[float, float]:
        """
        Solid slab (one-way, two-way, flat slab).

        Formulae
        --------
        Concrete : h × plan_area
        Formwork : plan_area  (soffit only)
        """
        h = g.get("h", 0) / 1000
        area = _plan_area(g)
        concrete = h * area
        formwork = area
        return concrete, formwork

    @staticmethod
    def _slab_ribbed(g: dict, notes: list) -> tuple[float, float]:
        """
        Ribbed slab.

        Formulae
        --------
        Concrete : (topping × area) + (rib_b × rib_h × rib_length × rib_count)
        Formwork : plan_area  (soffit of ribs + topping)
        """
        topping = g.get("topping_h", 75) / 1000      # mm → m
        area = _plan_area(g)
        rib_b = g.get("rib_b", 125) / 1000
        rib_h = g.get("rib_h", 200) / 1000
        rib_length = g.get("span_mm", g.get("lx", 0)) / 1000
        rib_spacing = g.get("rib_spacing", 400) / 1000
        rib_count = int(area / rib_spacing) if rib_spacing > 0 else 0

        concrete = (topping * area) + (rib_b * rib_h * rib_length * rib_count)
        formwork = area
        notes.append(f"Ribbed slab: {rib_count} ribs at {rib_spacing*1000:.0f} mm c/c.")
        return concrete, formwork

    @staticmethod
    def _slab_waffle(g: dict, notes: list) -> tuple[float, float]:
        """
        Waffle slab.

        Formulae
        --------
        Concrete : (topping × area) + X-ribs + Y-ribs − junction overlaps
        Formwork : plan_area
        """
        topping = g.get("topping_h", 75) / 1000
        area = _plan_area(g)
        rib_b = g.get("rib_b", 125) / 1000
        rib_h = g.get("rib_h", 200) / 1000
        rib_spacing = g.get("rib_spacing", 400) / 1000

        lx = g.get("lx", g.get("span_mm", 4000)) / 1000
        ly = g.get("ly", lx) / 1000 if "ly" in g else lx

        nx = int(lx / rib_spacing) if rib_spacing > 0 else 0
        ny = int(ly / rib_spacing) if rib_spacing > 0 else 0

        x_rib_vol = rib_b * rib_h * lx * ny
        y_rib_vol = rib_b * rib_h * ly * nx
        junction_vol = rib_b * rib_b * rib_h * nx * ny  # subtract junction overlaps
        concrete = (topping * area) + x_rib_vol + y_rib_vol - junction_vol
        formwork = area
        notes.append(f"Waffle slab: {nx}×{ny} rib grid.")
        return concrete, formwork

    @staticmethod
    def _column(g: dict, notes: list) -> tuple[float, float]:
        """
        Column.

        Formulae
        --------
        Concrete : b × h × storey_height
        Formwork : perimeter × storey_height  (4 faces)
        """
        b = g.get("b", 0) / 1000
        h = g.get("h", 0) / 1000
        height = g.get("storey_height_mm", g.get("height_mm", 3000)) / 1000
        concrete = b * h * height
        formwork = 2 * (b + h) * height
        return concrete, formwork

    @staticmethod
    def _wall(g: dict, notes: list) -> tuple[float, float]:
        """
        Reinforced concrete wall.

        Formulae
        --------
        Concrete : thickness × length × height
        Formwork : 2 × length × height  (both faces)
        """
        t = g.get("thickness_mm", g.get("b", 200)) / 1000
        length = g.get("length_mm", g.get("lx", 1000)) / 1000
        height = g.get("height_mm", 3000) / 1000
        concrete = t * length * height
        formwork = 2 * length * height
        return concrete, formwork

    @staticmethod
    def _footing_pad(g: dict, notes: list) -> tuple[float, float]:
        """
        Pad footing or pile cap.

        Formulae
        --------
        Concrete : lx × ly × h
        Formwork : 2(lx + ly) × h  (sides only — bottom on soil/blinding)
        """
        lx = g.get("lx", 0) / 1000
        ly = g.get("ly", lx * 1000) / 1000 if "ly" in g else lx
        h = g.get("h", 0) / 1000
        concrete = lx * ly * h
        formwork = 2 * (lx + ly) * h
        notes.append("Formwork: sides only (bottom on blinding).")
        return concrete, formwork

    @staticmethod
    def _staircase(g: dict, notes: list) -> tuple[float, float]:
        """
        Staircase flight.

        Formulae
        --------
        Concrete (waist slab) : waist × slope_length × width
        Concrete (steps)      : 0.5 × going × riser × width × nsteps
        Formwork              : slope_length × width  (soffit)
        """
        waist = g.get("waist_mm", 150) / 1000
        going = g.get("going_mm", 275) / 1000
        riser = g.get("riser_mm", 175) / 1000
        width = g.get("width_mm", 1200) / 1000
        nsteps = g.get("num_steps", 12)
        h_flight = riser * nsteps
        l_plan = going * nsteps
        slope_length = math.sqrt(l_plan ** 2 + h_flight ** 2)

        waist_vol = waist * slope_length * width
        steps_vol = 0.5 * going * riser * width * nsteps
        concrete = waist_vol + steps_vol

        formwork = slope_length * width
        notes.append(f"Staircase: {nsteps} steps, going={going*1000:.0f} mm, riser={riser*1000:.0f} mm.")
        return concrete, formwork

    # ------------------------------------------------------------------ aggregation

    @staticmethod
    def _steel_by_member(rebar_schedule: dict) -> dict[str, float]:
        """Sum total steel mass per member_id from the rebar schedule."""
        by_member: dict[str, float] = {}
        for mid, rows in rebar_schedule.get("by_member", {}).items():
            by_member[mid] = sum(r.get("mass_kg", 0.0) for r in rows)
        return by_member

    @staticmethod
    def _group_summary(mqs: list[MemberQuantities], attr: str) -> dict[str, dict]:
        """Group and sum quantities by a member attribute (type or floor)."""
        summary: dict[str, dict] = {}
        for mq in mqs:
            key = getattr(mq, attr, "Unknown")
            if key not in summary:
                summary[key] = {"concrete_m3": 0.0, "formwork_m2": 0.0, "steel_kg": 0.0}
            s = summary[key]
            s["concrete_m3"] = round(s["concrete_m3"] + mq.concrete_m3, 3)
            s["formwork_m2"] = round(s["formwork_m2"] + mq.formwork_m2, 2)
            s["steel_kg"] = round(s["steel_kg"] + mq.steel_kg, 1)
        return summary

    @staticmethod
    def _grand_total(mqs: list[MemberQuantities]) -> dict:
        """Compute project-wide totals."""
        return {
            "concrete_m3": round(sum(m.concrete_m3 for m in mqs), 3),
            "formwork_m2": round(sum(m.formwork_m2 for m in mqs), 2),
            "steel_kg": round(sum(m.steel_kg for m in mqs), 1),
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _plan_area(g: dict) -> float:
    """
    Compute plan area (m²) from geometry dict.

    Tries: lx × ly, then span × width, with sensible fallback.

    Parameters
    ----------
    g : dict
        Member geometry dict.

    Returns
    -------
    float
        Plan area in square metres.
    """
    lx = g.get("lx", g.get("span_mm", g.get("length_mm", 0)))
    ly = g.get("ly", g.get("width_mm", lx))
    return (lx / 1000.0) * (ly / 1000.0)

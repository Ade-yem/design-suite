"""
Module 2 — Reinforcement Schedule Engine
=========================================
Aggregates reinforcement data from all members in a ``ReportDataModel`` and
produces a BS 8666:2020-compliant bar schedule.

The engine reads the ``reinforcement`` field on each ``ReportMember`` and
assembles schedule rows. It never calculates reinforcement areas — it only
formats and aggregates.

Key features
------------
* Produces bar schedule rows with: Bar Mark, Member, Type, Diameter, Count,
  Shape Code, Cut Lengths (A–E), Total Length, and Mass.
* Mass calculated using the standard unit mass table (kg/m) per diameter.
* Supports grouping at four levels: per member, per floor, per member type,
  and project total.

Classes
-------
RebarScheduleEngine
    Main entry point. ``build(rdm)`` returns a complete schedule data dict.
BarRow
    Dataclass representing one row in the BS 8666 bar schedule table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from services.reporting.normalizer import ReportDataModel, ReportMember


# ---------------------------------------------------------------------------
# BS 8666:2020 — Unit mass table (kg/m) by nominal diameter (mm)
# ---------------------------------------------------------------------------
BAR_UNIT_MASS: dict[int, float] = {
    6:   0.222,
    8:   0.395,
    10:  0.616,
    12:  0.888,
    16:  1.579,
    20:  2.466,
    25:  3.854,
    32:  6.313,
    40:  9.864,
    50: 15.413,
}


def unit_mass(diameter_mm: int) -> float:
    """
    Return the steel unit mass (kg/m) for a given bar diameter.

    Parameters
    ----------
    diameter_mm : int
        Nominal bar diameter in millimetres.

    Returns
    -------
    float
        Unit mass in kg/m. Returns 0.0 if diameter is not in the standard table
        (with a graceful fallback using the formula m = 0.00617 × d² kg/m).
    """
    if diameter_mm in BAR_UNIT_MASS:
        return BAR_UNIT_MASS[diameter_mm]
    # Formula fallback: m = ρ × A = 7850 × (π/4 × d²) = 0.00617 d² (approx)
    return round(0.00617 * diameter_mm ** 2, 3)


# ---------------------------------------------------------------------------
# BarRow — one row of the BS 8666 bar schedule
# ---------------------------------------------------------------------------

@dataclass
class BarRow:
    """
    Represents one row of the BS 8666:2020 reinforcement bar schedule.

    Parameters
    ----------
    bar_mark : str
        Unique bar mark identifier (e.g. "B12-01").
    member_id : str
        The structural member this bar belongs to (e.g. "B-12").
    member_type : str
        Structural type (e.g. "beam", "column").
    floor_level : str
        Floor level description.
    bar_type : str
        Bar category: "Main", "Link", "Distribution", or "Torsion".
    diameter_mm : int
        Nominal bar diameter (mm).
    num_members : int
        Number of identical members containing this bar.
    num_per_member : int
        Number of bars of this mark in each member.
    shape_code : str
        BS 8666 shape code (e.g. "00" for straight, "60" for link).
    cut_length_mm : float
        Total bending length / cut length per bar (mm).
    A_mm : float
        Dimension A (mm). Required for all bars.
    B_mm : Optional[float]
        Dimension B (mm). None if not applicable.
    C_mm : Optional[float]
        Dimension C (mm). None if not applicable.
    D_mm : Optional[float]
        Dimension D (mm). None if not applicable.
    E_mm : Optional[float]
        Dimension E (mm). None if not applicable.

    Derived Properties
    ------------------
    total_number : int
        num_members × num_per_member.
    total_length_m : float
        total_number × cut_length_mm / 1000.
    mass_kg : float
        total_length_m × unit_mass(diameter_mm).
    """

    bar_mark: str
    member_id: str
    member_type: str
    floor_level: str
    bar_type: str
    diameter_mm: int
    num_members: int
    num_per_member: int
    shape_code: str
    cut_length_mm: float
    A_mm: float
    B_mm: Optional[float] = None
    C_mm: Optional[float] = None
    D_mm: Optional[float] = None
    E_mm: Optional[float] = None

    @property
    def total_number(self) -> int:
        """Total quantity of this bar across all members."""
        return self.num_members * self.num_per_member

    @property
    def total_length_m(self) -> float:
        """Total steel length in metres."""
        return round(self.total_number * self.cut_length_mm / 1000.0, 2)

    @property
    def mass_kg(self) -> float:
        """Total steel mass in kilograms."""
        return round(self.total_length_m * unit_mass(self.diameter_mm), 1)

    def as_dict(self) -> dict:
        """
        Serialize this bar row to a plain dict for template rendering.

        Returns
        -------
        dict
            All fields plus derived properties (total_number, total_length_m,
            mass_kg).
        """
        return {
            "bar_mark": self.bar_mark,
            "member_id": self.member_id,
            "member_type": self.member_type,
            "floor_level": self.floor_level,
            "bar_type": self.bar_type,
            "diameter_mm": self.diameter_mm,
            "num_members": self.num_members,
            "num_per_member": self.num_per_member,
            "total_number": self.total_number,
            "shape_code": self.shape_code,
            "cut_length_mm": self.cut_length_mm,
            "A_mm": self.A_mm,
            "B_mm": self.B_mm or "—",
            "C_mm": self.C_mm or "—",
            "D_mm": self.D_mm or "—",
            "E_mm": self.E_mm or "—",
            "total_length_m": self.total_length_m,
            "mass_kg": self.mass_kg,
        }


# ---------------------------------------------------------------------------
# Reinforcement Schedule Engine
# ---------------------------------------------------------------------------

class RebarScheduleEngine:
    """
    Module 2: Reinforcement Schedule Engine.

    Produces a complete, BS 8666:2020-compliant bar schedule from the
    reinforcement data embedded in a ``ReportDataModel``.

    The engine is purely a formatter and aggregator. It reads bar data from
    ``member.reinforcement`` and converts it into ``BarRow`` objects, then
    groups them at multiple levels.

    Usage
    -----
    ::

        engine = RebarScheduleEngine()
        schedule = engine.build(rdm)
        # schedule["rows"]        → list[dict] — all bar rows
        # schedule["by_member"]   → dict[member_id, list[dict]]
        # schedule["by_floor"]    → dict[floor_level, list[dict]]
        # schedule["by_type"]     → dict[member_type, list[dict]]
        # schedule["project_total"] → {steel_kg, total_length_m, by_diameter}
    """

    def build(self, rdm: ReportDataModel) -> dict[str, Any]:
        """
        Build the complete reinforcement schedule from the Report Data Model.

        Parameters
        ----------
        rdm : ReportDataModel
            The fully normalised report data model.

        Returns
        -------
        dict with keys:
            rows : list[dict]
                Flat list of all bar schedule rows (serialised BarRow dicts).
            by_member : dict[str, list[dict]]
                Rows grouped by member_id.
            by_floor : dict[str, list[dict]]
                Rows grouped by floor_level.
            by_type : dict[str, list[dict]]
                Rows grouped by member_type.
            project_total : dict
                Aggregate: total steel mass (kg), total length (m),
                breakdown by bar diameter.
        """
        all_rows: list[BarRow] = []

        for member in rdm.members:
            rows = self._extract_rows(member)
            all_rows.extend(rows)

        row_dicts = [r.as_dict() for r in all_rows]

        return {
            "rows": row_dicts,
            "by_member": self._group_by(row_dicts, "member_id"),
            "by_floor": self._group_by(row_dicts, "floor_level"),
            "by_type": self._group_by(row_dicts, "member_type"),
            "project_total": self._total(all_rows),
        }

    # ------------------------------------------------------------------ private

    @staticmethod
    def _extract_rows(member: ReportMember) -> list[BarRow]:
        """Extract BarRow objects from a member's reinforcement dict."""
        rows: list[BarRow] = []
        rebar = member.reinforcement

        # Main bars
        for i, bar in enumerate(rebar.get("main_bars", []), start=1):
            row = RebarScheduleEngine._bar_to_row(bar, member, "Main", i)
            if row:
                rows.append(row)

        # Links
        for i, bar in enumerate(rebar.get("links", []), start=1):
            row = RebarScheduleEngine._bar_to_row(bar, member, "Link", i)
            if row:
                rows.append(row)

        # Distribution bars
        for i, bar in enumerate(rebar.get("distribution_bars", []), start=1):
            row = RebarScheduleEngine._bar_to_row(bar, member, "Distribution", i)
            if row:
                rows.append(row)

        return rows

    @staticmethod
    def _bar_to_row(
        bar: dict, member: ReportMember, bar_type: str, seq: int
    ) -> Optional[BarRow]:
        """Convert a raw bar dict to a BarRow. Returns None if data is insufficient."""
        # Use existing mark or generate one
        mark = bar.get("mark") or f"{member.member_id}-{bar_type[0]}{seq:02d}"
        dia = bar.get("diameter_mm")
        if not dia:
            return None  # Cannot schedule without diameter

        cut_length = bar.get("cut_length_mm", 0.0)
        count = bar.get("count", 1)
        shape_code = bar.get("shape_code", "00")

        # Dimension fields (A = minimum = cut length for straight bar)
        A = bar.get("A_mm", cut_length)
        B = bar.get("B_mm")
        C = bar.get("C_mm")
        D = bar.get("D_mm")
        E = bar.get("E_mm")

        return BarRow(
            bar_mark=mark,
            member_id=member.member_id,
            member_type=member.member_type,
            floor_level=member.floor_level,
            bar_type=bar_type,
            diameter_mm=int(dia),
            num_members=1,
            num_per_member=count,
            shape_code=shape_code,
            cut_length_mm=float(cut_length),
            A_mm=float(A) if A else 0.0,
            B_mm=float(B) if B else None,
            C_mm=float(C) if C else None,
            D_mm=float(D) if D else None,
            E_mm=float(E) if E else None,
        )

    @staticmethod
    def _group_by(rows: list[dict], key: str) -> dict[str, list[dict]]:
        """Group a list of row dicts by a given key."""
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            k = str(row.get(key, "Unknown"))
            grouped.setdefault(k, []).append(row)
        return grouped

    @staticmethod
    def _total(rows: list[BarRow]) -> dict:
        """Compute aggregate totals across all bar rows."""
        total_mass = sum(r.mass_kg for r in rows)
        total_length = sum(r.total_length_m for r in rows)
        by_dia: dict[int, dict] = {}
        for r in rows:
            d = r.diameter_mm
            if d not in by_dia:
                by_dia[d] = {"length_m": 0.0, "mass_kg": 0.0}
            by_dia[d]["length_m"] = round(by_dia[d]["length_m"] + r.total_length_m, 2)
            by_dia[d]["mass_kg"] = round(by_dia[d]["mass_kg"] + r.mass_kg, 1)
        return {
            "total_mass_kg": round(total_mass, 1),
            "total_length_m": round(total_length, 2),
            "by_diameter": dict(sorted(by_dia.items())),
        }

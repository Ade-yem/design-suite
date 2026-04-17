"""
Module 5 — Project Summary Engine
====================================
Generates a one-page executive summary context for the entire structural design.

Content
-------
1. Project details block.
2. Structural system description (auto-generated from member types present).
3. Floor-by-floor member schedule (member counts and types per level).
4. Global material quantities summary table.
5. Design code summary.
6. Outstanding actions (from compliance report).

Classes
-------
ProjectSummaryEngine
    Main entry point. ``build(rdm, quantities, compliance)`` returns the
    summary context dict for template rendering.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from services.reporting.normalizer import ReportDataModel


# ---------------------------------------------------------------------------
# Structural system descriptions — auto-generated from member types
# ---------------------------------------------------------------------------

_SYSTEM_DESCRIPTIONS: dict[str, str] = {
    "beam": "reinforced concrete beam frame",
    "column": "reinforced concrete column system",
    "slab_one_way": "one-way spanning solid RC slabs",
    "slab_two_way": "two-way spanning solid RC slabs",
    "slab_ribbed": "ribbed RC slab system",
    "slab_waffle": "waffle slab system",
    "slab_flat": "flat slab system",
    "wall": "reinforced concrete shear walls",
    "footing_pad": "isolated pad foundations",
    "footing_pile": "pile cap foundations",
    "staircase": "reinforced concrete staircases",
}

_MEMBER_TYPE_LABELS: dict[str, str] = {
    "beam": "Beams",
    "column": "Columns",
    "slab_one_way": "One-Way Slabs",
    "slab_two_way": "Two-Way Slabs",
    "slab_ribbed": "Ribbed Slabs",
    "slab_waffle": "Waffle Slabs",
    "slab_flat": "Flat Slabs",
    "wall": "Walls",
    "footing_pad": "Pad Footings",
    "footing_pile": "Pile Caps",
    "staircase": "Staircases",
}


class ProjectSummaryEngine:
    """
    Module 5: Project Summary Engine.

    Assembles a one-page executive summary context from the fully processed
    Report Data Model and the outputs of Modules 3 and 4.

    This module reads prepared data only — it never calculates.

    Usage
    -----
    ::

        engine = ProjectSummaryEngine()
        summary = engine.build(rdm, quantities_context, compliance_context)
        # Pass summary to TemplateRenderer.render_summary(summary)
    """

    def build(
        self,
        rdm: ReportDataModel,
        quantities: dict[str, Any],
        compliance: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build the project summary context.

        Parameters
        ----------
        rdm : ReportDataModel
            The fully normalised report data model.
        quantities : dict
            Output of ``MaterialQuantityEngine.build(rdm, rebar_schedule)``.
            Used for the global material summary table.
        compliance : dict
            Output of ``ComplianceReportEngine.build(rdm)``.
            Used for outstanding actions and code summary.

        Returns
        -------
        dict with keys:
            project : ReportProject
                Project metadata.
            structural_system : str
                Human-readable description of the structural system.
            member_type_counts : dict[str, int]
                Count of members per type.
            floor_schedule : list[dict]
                Per-floor member-type breakdown.
                Each: {floor_level, member_counts: dict[type, int]}.
            material_summary : dict
                Grand total quantities from Module 3.
            material_summary_by_type : dict
                Per-type quantities from Module 3.
            design_code_summary : dict
                Code compliance summary from Module 4.
            outstanding_actions : list[str]
                Human-readable list of actions before sign-off.
        """
        return {
            "project": rdm.project,
            "structural_system": self._structural_system(rdm),
            "member_type_counts": self._member_type_counts(rdm),
            "floor_schedule": self._floor_schedule(rdm),
            "material_summary": quantities.get("grand_total", {}),
            "material_summary_by_type": quantities.get("summary_by_type", {}),
            "design_code_summary": compliance.get("code_compliance", {}),
            "outstanding_actions": self._outstanding_actions(compliance),
        }

    # ------------------------------------------------------------------ private

    @staticmethod
    def _structural_system(rdm: ReportDataModel) -> str:
        """Generate a human-readable description of the structural system."""
        types_present = {m.member_type.lower() for m in rdm.members}
        parts = [
            _SYSTEM_DESCRIPTIONS[t]
            for t in _SYSTEM_DESCRIPTIONS
            if t in types_present
        ]
        if not parts:
            return "Reinforced concrete structure."
        if len(parts) == 1:
            return f"The structure employs {parts[0]}."
        main = parts[:-1]
        last = parts[-1]
        return f"The structure employs {', '.join(main)}, and {last}."

    @staticmethod
    def _member_type_counts(rdm: ReportDataModel) -> dict[str, int]:
        """Return count of members per type with human-readable labels."""
        raw_counts: Counter[str] = Counter(m.member_type for m in rdm.members)
        return {
            _MEMBER_TYPE_LABELS.get(t, t): count
            for t, count in sorted(raw_counts.items())
        }

    @staticmethod
    def _floor_schedule(rdm: ReportDataModel) -> list[dict]:
        """
        Build a per-floor member schedule.

        Returns
        -------
        list[dict]
            Sorted by floor level. Each dict:
            {floor_level, member_counts: dict[label, int], total_members: int}.
        """
        # Group members by floor
        by_floor: dict[str, Counter] = {}
        for m in rdm.members:
            fl = m.floor_level
            if fl not in by_floor:
                by_floor[fl] = Counter()
            by_floor[fl][m.member_type] += 1

        schedule = []
        for floor, counts in sorted(by_floor.items()):
            schedule.append({
                "floor_level": floor,
                "member_counts": {
                    _MEMBER_TYPE_LABELS.get(t, t): c
                    for t, c in sorted(counts.items())
                },
                "total_members": sum(counts.values()),
            })
        return schedule

    @staticmethod
    def _outstanding_actions(compliance: dict) -> list[str]:
        """
        Compile a list of outstanding actions from the compliance context.

        Returns
        -------
        list[str]
            Human-readable action items.
        """
        actions: list[str] = []

        failed = compliance.get("failed_checks", [])
        if failed:
            member_ids = list({f["member_id"] for f in failed})
            actions.append(
                f"Redesign {len(failed)} failed check(s) on members: "
                f"{', '.join(member_ids[:5])}{'...' if len(member_ids) > 5 else ''}."
            )

        defaulted = compliance.get("defaulted_inputs", [])
        if defaulted:
            params = [d["parameter"] for d in defaulted]
            actions.append(
                f"Confirm {len(defaulted)} assumed input(s): "
                f"{', '.join(params[:4])}{'...' if len(params) > 4 else ''} before sign-off."
            )

        near = compliance.get("near_limit_warnings", [])
        if near:
            actions.append(
                f"Review {len(near)} near-limit check(s) — utilisation ≥ 95 %."
            )

        if not actions:
            actions.append("No outstanding actions. Design ready for sign-off.")

        return actions

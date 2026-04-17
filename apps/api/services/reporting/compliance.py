"""
Module 4 — Compliance Report Engine
=====================================
Generates a structured compliance summary for the entire project, flagging:

1. **Failed checks** — any member where any limit state check returned FAIL.
2. **Near-limit warnings** — any check within 5 % of capacity.
3. **Defaulted inputs** — any value assumed by the system rather than supplied
   by the engineer.
4. **Code compliance confirmation** — count of members passed/failed.

This module is generated alongside (never instead of) calculation sheets.

Classes
-------
ComplianceReportEngine
    Main entry point. ``build(rdm)`` returns a structured compliance context dict.
"""

from __future__ import annotations

from typing import Any

from services.reporting.normalizer import ReportDataModel, ReportMember


class ComplianceReportEngine:
    """
    Module 4: Compliance Report Engine.

    Scans every ``ReportMember`` in the ``ReportDataModel`` and assembles a
    structured compliance report context for template rendering.

    The engine reads pre-parsed data from the normalised members (failed_checks,
    near_limit_checks, defaulted_inputs). It never re-evaluates design results.

    Usage
    -----
    ::

        engine = ComplianceReportEngine()
        context = engine.build(rdm)
        # context["failed_checks"]       → list[dict]
        # context["near_limit_warnings"] → list[dict]
        # context["defaulted_inputs"]    → list[dict]
        # context["code_compliance"]     → dict
    """

    NEAR_LIMIT_THRESHOLD_PCT = 95.0  # ≥ 95% utilisation triggers warning

    def build(self, rdm: ReportDataModel) -> dict[str, Any]:
        """
        Build the compliance report context from the Report Data Model.

        Parameters
        ----------
        rdm : ReportDataModel
            The fully normalised report data model containing all members.

        Returns
        -------
        dict with keys:
            project : ReportProject
                Project metadata for header rendering.
            failed_checks : list[dict]
                Each dict: {member_id, check, actual, limit, units, floor_level}.
            near_limit_warnings : list[dict]
                Each dict: {member_id, check, utilisation_pct, note, floor_level}.
            defaulted_inputs : list[dict]
                Deduplicated list of assumed inputs with affected member IDs.
                Each dict: {parameter, default_used, affected_member_ids}.
            code_compliance : dict
                {code, members_checked, members_passed, members_failed}.
            global_warnings : list[str]
                Project-level warnings from the normalizer.
        """
        failed_checks = self._collect_failed(rdm.members)
        near_limit = self._collect_near_limit(rdm.members)
        defaulted = self._collect_defaulted(rdm.members)
        code_summary = self._code_compliance(rdm)

        return {
            "project": rdm.project,
            "failed_checks": failed_checks,
            "near_limit_warnings": near_limit,
            "defaulted_inputs": defaulted,
            "code_compliance": code_summary,
            "global_warnings": rdm.global_warnings,
            "has_failures": len(failed_checks) > 0,
            "action_required": len(failed_checks) > 0,
        }

    # ------------------------------------------------------------------ private

    @staticmethod
    def _collect_failed(members: list[ReportMember]) -> list[dict]:
        """
        Collect all failed limit state checks across all members.

        Returns
        -------
        list[dict]
            Each dict: {member_id, floor_level, check, actual, limit, units}.
        """
        rows: list[dict] = []
        for m in members:
            for fc in m.failed_checks:
                rows.append({
                    "member_id": m.member_id,
                    "floor_level": m.floor_level,
                    "member_type": m.member_type,
                    "check": fc.get("check", "—"),
                    "actual": fc.get("actual", "—"),
                    "limit": fc.get("limit", "—"),
                    "units": fc.get("units", ""),
                })
        return rows

    @staticmethod
    def _collect_near_limit(members: list[ReportMember]) -> list[dict]:
        """
        Collect near-limit warnings across all members.

        Returns
        -------
        list[dict]
            Each dict: {member_id, floor_level, check, utilisation_pct, note}.
        """
        rows: list[dict] = []
        for m in members:
            for nl in m.near_limit_checks:
                rows.append({
                    "member_id": m.member_id,
                    "floor_level": m.floor_level,
                    "check": nl.get("check", "—"),
                    "utilisation_pct": nl.get("utilisation_pct", "—"),
                    "note": nl.get("note", ""),
                })
        return rows

    @staticmethod
    def _collect_defaulted(members: list[ReportMember]) -> list[dict]:
        """
        Collect and deduplicate defaulted input assumptions across all members.

        Multiple members sharing the same default assumption are consolidated
        into a single row with the full list of affected member IDs.

        Returns
        -------
        list[dict]
            Each dict: {parameter, default_used, affected_member_ids, source}.
        """
        # key → (parameter, default_used, source) → list of member IDs
        registry: dict[str, dict] = {}
        for m in members:
            for di in m.defaulted_inputs:
                param = di.get("parameter", "Unknown")
                default = str(di.get("default_used", "—"))
                source = di.get("source", "system default")
                key = f"{param}::{default}"
                if key not in registry:
                    registry[key] = {
                        "parameter": param,
                        "default_used": default,
                        "source": source,
                        "affected_member_ids": [],
                    }
                registry[key]["affected_member_ids"].append(m.member_id)

        return list(registry.values())

    @staticmethod
    def _code_compliance(rdm: ReportDataModel) -> dict:
        """
        Summarise design code compliance across all members.

        Returns
        -------
        dict with keys:
            code : str — the design code applied.
            members_checked : int — total number of members.
            members_passed : int — members with status "PASS".
            members_failed : int — members with status "FAIL".
        """
        total = len(rdm.members)
        failed = sum(1 for m in rdm.members if m.status == "FAIL")
        passed = total - failed
        return {
            "code": rdm.project.design_code,
            "code_edition": rdm.project.design_code_edition,
            "members_checked": total,
            "members_passed": passed,
            "members_failed": failed,
        }

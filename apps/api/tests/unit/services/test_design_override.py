"""
tests/unit/services/test_design_override.py
============================================
Service-level tests for ``DesignService.apply_override`` — specifically that a
reinforcement/section override re-runs the design (rather than only merging
fields) so the returned reinforcement reflects the change. This underpins the
frontend rebar click-to-edit flow.
"""
from __future__ import annotations

import pytest

from services.design import design_service
from services.files import file_service
from storage.stage_result_store import stage_result_store
from core.design.rc import design_member


PID = "PRJ-OVERRIDE-TEST"

_ANALYSIS_MEMBER = {
    "member_id": "B1",
    "member_type": "beam",
    "stress_resultants": {
        "M_max_sagging_kNm": 180.0,
        "M_max_hogging_kNm": 0.0,
        "V_max_kN": 120.0,
        "N_axial_kN": 0.0,
    },
}


async def _seed_project() -> None:
    """Seed parsed geometry, analysis and an initial design for one beam."""
    await file_service.register_geometry(
        PID,
        {
            "members": [
                {"member_id": "B1", "member_type": "beam",
                 "meta": {"member_type": "beam", "b_mm": 300, "h_mm": 600,
                          "cover_mm": 30, "bar_dia_mm": 20}},
            ],
            "scale": {"factor": 1.0, "unit": "mm", "confirmed": True},
        },
    )
    stage_result_store._memory_store[(PID, "analysis")] = {
        "members": [_ANALYSIS_MEMBER],
        "design_code": "BS8110",
    }
    initial = design_member(
        _ANALYSIS_MEMBER,
        {"member_type": "beam", "b_mm": 300, "h_mm": 600, "cover_mm": 30, "bar_dia_mm": 20},
        "BS8110",
    )
    initial["member_id"] = "B1"
    stage_result_store._memory_store[(PID, "design")] = {
        "design_id": "DES-TEST",
        "design_code": "BS8110",
        "member_count": 1,
        "members": [initial],
        "generated_at": "2026-01-01T00:00:00Z",
    }


class TestApplyOverrideRecompute:
    async def test_bar_size_override_recomputes_reinforcement(self):
        await _seed_project()

        outcome = await design_service.apply_override(
            PID, "B1",
            override={"meta_updates": {"bar_dia_mm": 32}, "reason": "use larger bars"},
        )
        result = outcome["result"]

        # The override is recorded and the design was actually recomputed.
        assert result["member_id"] == "B1"
        assert result["override_reason"] == "use larger bars"
        assert "As_req" in result and result["status"] != "skipped"

        # The recompute must match a direct design_member call with the merged meta.
        expected = design_member(
            _ANALYSIS_MEMBER,
            {"member_type": "beam", "b_mm": 300, "h_mm": 600, "cover_mm": 30, "bar_dia_mm": 32},
            "BS8110",
        )
        assert result["reinforcement_description"] == expected["reinforcement_description"]

    async def test_section_override_changes_required_steel(self):
        await _seed_project()

        before = design_service.get_results(PID)["members"][0]["As_req"]
        outcome = await design_service.apply_override(
            PID, "B1",
            override={"h_mm": 900, "reason": "deepen beam"},
        )
        # A deeper section needs less tension steel for the same moment.
        assert outcome["result"]["As_req"] <= before

    async def test_unknown_member_raises_keyerror(self):
        await _seed_project()
        with pytest.raises(KeyError):
            await design_service.apply_override(PID, "NOPE", override={"reason": "x"})

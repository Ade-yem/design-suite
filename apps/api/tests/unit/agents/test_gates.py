"""
tests/unit/agents/test_gates.py
===============================
Unit tests for the four human-in-the-loop gate routers and gate node outputs.

These guard the safety contract: a gate only advances ("confirmed"/"passed")
when its confirmation flag is set, and otherwise reports "waiting". The
designer/drawing routers additionally divert to re-analysis when a self-weight
change is flagged.
"""
from __future__ import annotations

import pytest

from agents import gates


class TestGeometryGate:
    def test_router_waits_until_verified(self):
        assert gates.geometry_gate_router({}) == "waiting"
        assert gates.geometry_gate_router({"geometry_verified": True}) == "confirmed"

    async def test_node_waiting_does_no_io(self):
        out = await gates.geometry_verification_gate({"project_id": "P1"})
        assert out["agent_logs"][0] == {"agent": "gate_1", "status": "waiting"}
        assert "messages" not in out

    async def test_node_passed_verifies_geometry(self, monkeypatch):
        calls = {}

        async def fake_verify(project_id, corrections=None, notes=None):
            calls["project_id"] = project_id
            calls["corrections"] = corrections

        monkeypatch.setattr(gates.file_service, "verify_geometry", fake_verify)
        out = await gates.geometry_verification_gate(
            {"project_id": "P1", "geometry_verified": True, "geometry_corrections": [{"x": 1}]}
        )
        assert calls == {"project_id": "P1", "corrections": [{"x": 1}]}
        assert out["agent_logs"][0]["status"] == "passed"
        assert out["messages"]


class TestLoadingGate:
    def test_router(self):
        assert gates.loading_gate_router({}) == "waiting"
        assert gates.loading_gate_router({"loading_confirmed": True}) == "confirmed"

    async def test_node_outputs(self):
        waiting = await gates.loading_confirmation_gate({})
        assert waiting["agent_logs"][0]["status"] == "waiting"
        passed = await gates.loading_confirmation_gate({"loading_confirmed": True})
        assert passed["agent_logs"][0]["status"] == "passed"


class TestDesignerRouter:
    def test_reanalysis_takes_priority(self):
        state = {"reanalysis_triggered": True, "design_complete": True, "design_confirmed": True}
        assert gates.designer_router(state) == "reanalysis_needed"

    def test_confirmed_when_complete_and_confirmed(self):
        assert gates.designer_router(
            {"design_complete": True, "design_confirmed": True}
        ) == "confirmed"

    def test_waiting_confirmation_when_complete_only(self):
        assert gates.designer_router({"design_complete": True}) == "waiting_confirmation"

    def test_waiting_when_incomplete(self):
        assert gates.designer_router({}) == "waiting"


class TestDrawingGate:
    def test_router_design_change_priority(self):
        assert gates.drawing_gate_router(
            {"reanalysis_triggered": True, "drawing_confirmed": True}
        ) == "design_change"

    def test_router_confirmed_and_waiting(self):
        assert gates.drawing_gate_router({"drawing_confirmed": True}) == "confirmed"
        assert gates.drawing_gate_router({}) == "waiting"

    async def test_node_passed_sets_report_complete(self):
        out = await gates.drawing_review_gate({"drawing_confirmed": True})
        assert out["report_complete"] is True
        assert out["agent_logs"][0]["status"] == "passed"

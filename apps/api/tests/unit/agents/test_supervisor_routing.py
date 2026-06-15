"""
tests/unit/agents/test_supervisor_routing.py
============================================
Unit tests for the Supervisor's deterministic routing and safety guards. The
LLM-driven ``supervisor_node`` is not exercised here (the routing decision is
delegated to pure helpers); these tests lock down the fallback mapping,
prerequisite clamping, and the design-override heuristic that keep the graph
from ever routing past an unmet gate.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.supervisor import (
    _fallback_node,
    _validate_and_clamp,
    supervisor_router,
    _is_design_override,
)


class TestFallbackNode:
    def test_maps_status_to_node(self):
        assert _fallback_node({"pipeline_status": "created"}) == "geometry"
        assert _fallback_node({"pipeline_status": "geometry_verified"}) == "analyst"
        assert _fallback_node({"pipeline_status": "analysis_complete"}) == "designer"
        assert _fallback_node({"pipeline_status": "report_generated"}) == "end"

    def test_unknown_status_falls_back_to_end(self):
        assert _fallback_node({"pipeline_status": "bogus"}) == "end"

    def test_missing_status_defaults_to_geometry(self):
        assert _fallback_node({}) == "geometry"


class TestValidateAndClamp:
    def test_unknown_node_clamped_to_fallback(self):
        state = {"pipeline_status": "created"}
        assert _validate_and_clamp("teleport", state) == "geometry"

    def test_proposed_node_with_unmet_prereqs_is_clamped(self):
        # designer requires geometry_verified + loading_confirmed + analysis_complete
        state = {"pipeline_status": "geometry_verified", "geometry_verified": True}
        assert _validate_and_clamp("designer", state) == "analyst"

    def test_proposed_node_with_met_prereqs_is_allowed(self):
        state = {
            "pipeline_status": "analysis_complete",
            "geometry_verified": True,
            "loading_confirmed": True,
            "analysis_complete": True,
        }
        assert _validate_and_clamp("designer", state) == "designer"

    def test_node_without_prereqs_always_allowed(self):
        assert _validate_and_clamp("end", {"pipeline_status": "created"}) == "end"


class TestSupervisorRouter:
    def test_returns_valid_next_node(self):
        assert supervisor_router({"next_node": "analyst"}) == "analyst"

    def test_invalid_next_node_falls_back_to_status_map(self):
        assert supervisor_router(
            {"next_node": "nope", "pipeline_status": "analysis_complete"}
        ) == "designer"

    def test_missing_next_node_falls_back(self):
        assert supervisor_router({"pipeline_status": "created"}) == "geometry"


class TestIsDesignOverride:
    def test_detects_change_with_dimension(self):
        assert _is_design_override(HumanMessage(content="change the width to 350mm")) is True

    def test_ignores_plain_question(self):
        assert _is_design_override(HumanMessage(content="what is the bending moment?")) is False

    def test_requires_both_verb_and_dimension(self):
        # has a verb but no dimension keyword
        assert _is_design_override(HumanMessage(content="please update the report")) is False

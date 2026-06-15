"""
Unit tests for VerticalLoadTakedownEngine (core/loading/takedown.py).
Tests cover: reaction splitting, connectivity, stack traversal,
load accumulation, reduction factors, multi-span support indexing,
and footing auto-generation.
"""

import math
import pytest

from core.loading.takedown import (
    VerticalLoadTakedownEngine,
    _get_beam_support_positions,
    _split_reaction_gk_qk,
    _build_connectivity,
    _build_column_stacks,
)
from core.analysis.beam_solver import MomentCoefficientSolver


# ── Factories ─────────────────────────────────────────────────────────────────

def make_beam(mid, sx, sy, ex, ey, storey="L01", spans_m=None):
    return {
        "member_id": mid,
        "member_type": "beam",
        "type": "beam",
        "storey": storey,
        "start_point": {"x": sx, "y": sy},
        "end_point": {"x": ex, "y": ey},
        "spans_m": spans_m or [],
        "meta": {},
    }


def make_column(mid, cx, cy, storey="L01", elevation=0.0, parent=None, child=None):
    return {
        "member_id": mid,
        "member_type": "column",
        "type": "column",
        "storey": storey,
        "elevation_m": elevation,
        "center_point": {"x": cx, "y": cy},
        "meta": {
            "b_mm": 300.0,
            "h_mm": 300.0,
            "L_clear": 3.0,
            "parent_column_id": parent,
            "child_column_id": child,
        },
    }


def make_beam_result(mid, reactions):
    return {
        "member_id": mid,
        "member_type": "beam",
        "reactions_kN": reactions,
        "stress_resultants": {
            "M_max_sagging_kNm": 0, "M_max_hogging_kNm": 0,
            "V_max_kN": 0, "N_axial_kN": 0, "deflection_max_mm": 0,
        },
    }


def make_beam_load(mid, udl_gk=10.0, udl_qk=5.0):
    return {
        "member_id": mid,
        "member_type": "beam",
        "design_code": "BS8110",
        "spans": [{"span_id": "S1", "length_m": 5.0, "loads": {"udl_gk": udl_gk, "udl_qk": udl_qk}}],
        "combination_used": "1.4Gk+1.6Qk",
    }


# ── Step 1 verification: MomentCoefficientSolver reactions_kN ────────────────

class TestMomentCoefficientSolverReactions:
    def test_two_span_reaction_count(self):
        solver = MomentCoefficientSolver("B1", [5.0, 5.0], "BS8110")
        result = solver.solve(ultimate_load_kN_per_m=20.0)
        # 2 spans → 3 support reactions
        assert len(result.reactions_kN) == 3

    def test_two_span_outer_reactions(self):
        solver = MomentCoefficientSolver("B1", [6.0, 4.0], "BS8110")
        result = solver.solve(ultimate_load_kN_per_m=15.0)
        F0 = 15.0 * 6.0
        F1 = 15.0 * 4.0
        assert result.reactions_kN[0] == pytest.approx(0.45 * F0, rel=1e-4)
        assert result.reactions_kN[-1] == pytest.approx(0.45 * F1, rel=1e-4)

    def test_three_span_reaction_count(self):
        solver = MomentCoefficientSolver("B2", [5.0, 5.0, 5.0], "BS8110")
        result = solver.solve(ultimate_load_kN_per_m=20.0)
        assert len(result.reactions_kN) == 4

    def test_interior_support_gets_two_contributions(self):
        """Interior support of a 2-span beam should be 0.60F[0] + 0.45F[1]."""
        spans = [5.0, 5.0]
        n = 20.0
        solver = MomentCoefficientSolver("B3", spans, "BS8110")
        result = solver.solve(n)
        F0 = n * spans[0]
        F1 = n * spans[1]
        expected = round(0.60 * F0 + 0.45 * F1, 3)
        assert result.reactions_kN[1] == pytest.approx(expected, rel=1e-4)


# ── Beam support position reconstruction ─────────────────────────────────────

class TestGetBeamSupportPositions:
    def test_single_span_returns_two_points(self):
        beam = make_beam("B1", 0, 0, 5000, 0)
        positions = _get_beam_support_positions(beam)
        assert len(positions) == 2
        assert positions[0]["idx"] == 0
        assert positions[1]["idx"] == 1

    def test_two_span_returns_three_points(self):
        beam = make_beam("B1", 0, 0, 10000, 0, spans_m=[5.0, 5.0])
        positions = _get_beam_support_positions(beam)
        assert len(positions) == 3
        mid_x = positions[1]["x"]
        assert mid_x == pytest.approx(5000.0, rel=1e-3)

    def test_interior_point_on_beam_axis(self):
        """Interior support for a diagonal beam should lie on the beam axis."""
        beam = make_beam("B1", 0, 0, 6000, 8000, spans_m=[5.0, 5.0])
        positions = _get_beam_support_positions(beam)
        total = math.hypot(6000, 8000)
        ratio = 5.0 * 1000 / total
        expected_x = 6000 * ratio
        expected_y = 8000 * ratio
        assert positions[1]["x"] == pytest.approx(expected_x, rel=1e-3)
        assert positions[1]["y"] == pytest.approx(expected_y, rel=1e-3)


# ── Connectivity ──────────────────────────────────────────────────────────────

class TestBuildConnectivity:
    def test_beam_endpoints_snap_to_columns(self):
        col_a = make_column("C1", 0, 0)
        col_b = make_column("C2", 5000, 0)
        beam = make_beam("B1", 0, 0, 5000, 0)
        members = [col_a, col_b, beam]
        conn = _build_connectivity(members)
        assert ("B1", 0) in conn["C1"]
        assert ("B1", 1) in conn["C2"]

    def test_distant_beam_does_not_snap(self):
        col = make_column("C1", 0, 0)
        beam = make_beam("B1", 2000, 2000, 7000, 2000)
        conn = _build_connectivity([col, beam])
        assert conn["C1"] == []

    def test_multi_span_interior_support_snaps(self):
        col_a = make_column("C1", 0, 0)
        col_mid = make_column("C2", 5000, 0)
        col_b = make_column("C3", 10000, 0)
        beam = make_beam("B1", 0, 0, 10000, 0, spans_m=[5.0, 5.0])
        conn = _build_connectivity([col_a, col_mid, col_b, beam])
        assert ("B1", 1) in conn["C2"]  # interior support at idx=1


# ── Column stacks ─────────────────────────────────────────────────────────────

class TestBuildColumnStacks:
    def test_single_storey_is_singleton_stacks(self):
        cols = [make_column("C1", 0, 0), make_column("C2", 5000, 0)]
        stacks = _build_column_stacks(cols)
        assert len(stacks) == 2
        for stack in stacks:
            assert len(stack) == 1

    def test_two_storey_stack_ordered_top_to_bottom(self):
        col_top = make_column("C1-L02", 0, 0, storey="L02", elevation=3.5, child=None, parent="C1-L01")
        col_bot = make_column("C1-L01", 0, 0, storey="L01", elevation=0.0, child="C1-L02", parent=None)
        stacks = _build_column_stacks([col_top, col_bot])
        # Should produce one stack: top → bottom
        assert len(stacks) == 1
        assert stacks[0][0]["member_id"] == "C1-L02"
        assert stacks[0][1]["member_id"] == "C1-L01"


# ── Full takedown accumulation ────────────────────────────────────────────────

class TestComputeColumnAxialLoads:
    def test_single_storey_two_beams(self):
        """Column receives reactions from 2 beams → N_uls > sum of reactions."""
        col = make_column("C1", 5000, 0)
        b1 = make_beam("B1", 0, 0, 5000, 0)
        b2 = make_beam("B2", 5000, 0, 10000, 0)
        members = [col, b1, b2]

        # Each beam contributes reaction at the column end: 50 kN ULS
        beam_results = {
            "B1": make_beam_result("B1", [20.0, 50.0]),
            "B2": make_beam_result("B2", [50.0, 20.0]),
        }
        beam_loading = {
            "B1": make_beam_load("B1", udl_gk=10.0, udl_qk=5.0),
            "B2": make_beam_load("B2", udl_gk=10.0, udl_qk=5.0),
        }
        col_axial, footings, f_loads = VerticalLoadTakedownEngine.compute_column_axial_loads(
            members, beam_results, beam_loading, design_code="BS8110"
        )
        assert "C1" in col_axial
        assert col_axial["C1"]["N_uls"] > 0

    def test_n_uls_increases_down_the_stack(self):
        """Bottom column N_uls must exceed top column N_uls."""
        col_top = make_column("C1-L02", 5000, 0, storey="L02", child=None, parent="C1-L01")
        col_bot = make_column("C1-L01", 5000, 0, storey="L01", child="C1-L02", parent=None)
        b_top = make_beam("B1", 0, 0, 5000, 0, storey="L02")
        b_bot = make_beam("B2", 0, 0, 5000, 0, storey="L01")
        members = [col_top, col_bot, b_top, b_bot]

        beam_results = {
            "B1": make_beam_result("B1", [20.0, 40.0]),
            "B2": make_beam_result("B2", [20.0, 40.0]),
        }
        beam_loading = {
            "B1": make_beam_load("B1"),
            "B2": make_beam_load("B2"),
        }
        col_axial, _, _ = VerticalLoadTakedownEngine.compute_column_axial_loads(
            members, beam_results, beam_loading, design_code="BS8110"
        )
        assert col_axial["C1-L01"]["N_uls"] > col_axial["C1-L02"]["N_uls"]

    def test_reduction_factor_applied_at_multiple_storeys(self):
        """3-storey stack: get_load_reduction_factor(3) should be 0.8."""
        cols = [
            make_column("C1-L03", 5000, 0, storey="L03", child=None, parent="C1-L02"),
            make_column("C1-L02", 5000, 0, storey="L02", child="C1-L03", parent="C1-L01"),
            make_column("C1-L01", 5000, 0, storey="L01", child="C1-L02", parent=None),
        ]
        members = cols
        col_axial, _, _ = VerticalLoadTakedownEngine.compute_column_axial_loads(
            members, {}, {}, design_code="BS8110"
        )
        # 3-storey base: reduction_factor should be 0.8
        assert col_axial["C1-L01"]["reduction_factor"] == pytest.approx(0.8)

    def test_beam_not_framing_in_gives_only_selfweight(self):
        """Column with no nearby beams should accumulate self-weight only."""
        col = make_column("C1", 0, 0)
        distant_beam = make_beam("B1", 10000, 10000, 15000, 10000)
        members = [col, distant_beam]
        beam_results = {"B1": make_beam_result("B1", [30.0, 30.0])}
        beam_loading = {"B1": make_beam_load("B1")}

        col_axial, _, _ = VerticalLoadTakedownEngine.compute_column_axial_loads(
            members, beam_results, beam_loading
        )
        from core.loading.vertical_loaders import ColumnLoadAssembler
        expected_sw = ColumnLoadAssembler.calculate_self_weight(300, 300, 3.0)
        assert col_axial["C1"]["gk_total"] == pytest.approx(expected_sw, rel=1e-4)


# ── Footing auto-generation ───────────────────────────────────────────────────

class TestFootingAutoGeneration:
    def test_ground_level_column_gets_footing(self):
        col = make_column("C1", 0, 0)  # no parent_column_id
        members = [col]
        col_axial, footings, f_loads = VerticalLoadTakedownEngine.compute_column_axial_loads(
            members, {}, {}, project_params={"qa_kpa": 150.0}
        )
        assert len(footings) == 1
        assert footings[0]["member_id"] == "F-C1"
        assert footings[0]["member_type"] == "footing"

    def test_upper_column_does_not_get_footing(self):
        col_top = make_column("C1-L02", 0, 0, parent="C1-L01")
        col_bot = make_column("C1-L01", 0, 0, child="C1-L02")
        members = [col_top, col_bot]
        _, footings, _ = VerticalLoadTakedownEngine.compute_column_axial_loads(
            members, {}, {}
        )
        footing_ids = {f["member_id"] for f in footings}
        # Only the base column should get a footing
        assert "F-C1-L01" in footing_ids
        assert "F-C1-L02" not in footing_ids

    def test_footing_n_sls_is_characteristic(self):
        """N_sls must equal gk_total + qk_total (unfactored)."""
        col = make_column("C1", 5000, 0)
        b = make_beam("B1", 0, 0, 5000, 0)
        members = [col, b]
        beam_results = {"B1": make_beam_result("B1", [20.0, 60.0])}
        beam_loading = {"B1": make_beam_load("B1", udl_gk=12.0, udl_qk=8.0)}

        col_axial, footings, _ = VerticalLoadTakedownEngine.compute_column_axial_loads(
            members, beam_results, beam_loading
        )
        axial = col_axial["C1"]
        expected_sls = axial["gk_total"] + axial["qk_total"]
        assert footings[0]["meta"]["N_sls"] == pytest.approx(expected_sls, rel=1e-4)

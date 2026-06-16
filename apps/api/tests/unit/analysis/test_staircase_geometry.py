"""
Storey-height-driven staircase geometry (Workstream B, Slice 3a).

A flight rises one storey, so its geometry must be derived from the storey
height — previously the solver used fixed defaults that ignored it.
"""
import pytest

from core.analysis.staircase_geometry import derive_flight_geometry


@pytest.mark.parametrize("h", [2.7, 3.0, 3.25, 4.0])
def test_risers_times_riser_equals_storey_height(h):
    g = derive_flight_geometry(h)
    reconstructed_m = g["num_risers"] * g["riser"] / 1000.0
    # Sub-millimetre agreement (riser is rounded to 2 dp).
    assert reconstructed_m == pytest.approx(h, abs=1e-3)


def test_going_respects_two_r_plus_g_and_minimum():
    g = derive_flight_geometry(3.0)
    assert g["going"] >= 250.0  # BS 8110 minimum going
    # 2R + G stays near the comfort relationship unless clamped to the minimum.
    assert 2 * g["riser"] + g["going"] >= 600.0 - 1.0


def test_taller_storey_yields_more_risers_and_longer_span():
    short = derive_flight_geometry(2.7)
    tall = derive_flight_geometry(4.0)
    assert tall["num_risers"] > short["num_risers"]
    assert tall["span_mm"] > short["span_mm"]


def test_engineer_overrides_win():
    g = derive_flight_geometry(3.0, riser=160, going=280, waist=175)
    assert g["riser"] == 160.0
    assert g["going"] == 280.0
    assert g["waist_mm"] == 175.0


def test_default_num_steps_is_one_fewer_than_risers():
    g = derive_flight_geometry(3.0)
    assert g["num_steps"] == g["num_risers"] - 1

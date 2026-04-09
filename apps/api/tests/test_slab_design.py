"""
Tests for BS 8110-1:1997 One-way and Two-way Slab Design.
"""
import pytest
from models.bs8110.slab import SlabSection
from services.design.bs8110.slab import (
    calculate_slab_reinforcement,
    get_two_way_moment_coefficients,
    get_two_way_shear_coefficients,
    design_one_way_slab,
    design_two_way_slab,
)


# ===========================================================================
# Model tests
# ===========================================================================

def test_slab_section_outer_layer():
    s = SlabSection(h=175, cover=25, fcu=30, lx=4000, ly=4000, fy=460)
    assert s.d == pytest.approx(175 - 25 - 6, abs=0.1)  # bar_dia=12 default


def test_slab_section_inner_layer():
    s = SlabSection(h=175, cover=25, fcu=30, lx=4000, ly=6000, fy=460,
                    slab_type="two-way", panel_type="interior",
                    layer="inner", bar_dia=12, bar_dia_outer=12)
    # d = 175 - 25 - 12 - 6 = 132
    assert s.d == pytest.approx(132, abs=0.1)


def test_slab_section_validates_ly_lx():
    with pytest.raises(ValueError, match="ly.*must be ≥ lx"):
        SlabSection(h=200, cover=25, fcu=30, lx=6000, ly=4000, fy=460)


def test_slab_section_two_way_requires_panel_type():
    with pytest.raises(ValueError, match="panel_type"):
        SlabSection(h=200, cover=25, fcu=30, lx=4000, ly=5000, fy=460,
                    slab_type="two-way")


# ===========================================================================
# Table look-up tests
# ===========================================================================

def test_table_3_14_interior_square():
    """Interior panel, ly/lx = 1.0 → βsx_neg = 0.031 per Table 3.14."""
    c = get_two_way_moment_coefficients("interior", 1.0)
    assert c["bsx_neg"] == pytest.approx(0.031, abs=0.001)
    assert c["bsx_pos"] == pytest.approx(0.024, abs=0.001)


def test_table_3_14_interpolation():
    """Interpolate between ratio 1.1 and 1.2 for four_discontinuous."""
    c = get_two_way_moment_coefficients("four_discontinuous", 1.15)
    # βsx_pos: 0.065 + 0.5*(0.074 - 0.065) = 0.0695
    assert c["bsx_pos"] == pytest.approx(0.0695, abs=0.001)


def test_table_3_15_lookup():
    c = get_two_way_shear_coefficients("interior", 1.0)
    # "interior" maps to "four_continuous" → βvx_cont = 0.33 at ly/lx=1.0
    assert c["bvx_cont"] == pytest.approx(0.33, abs=0.01)


# ===========================================================================
# One-way slab design tests
# ===========================================================================

def test_one_way_simple_slab():
    section = SlabSection(
        h=150, cover=25, fcu=30, lx=3500, ly=3500, fy=460,
        slab_type="one-way", support_condition="simple"
    )
    n = 8.55e-3   # N/mm² = 8.55 kN/m²
    res = calculate_slab_reinforcement(section, n)
    assert res["status"] == "OK"
    assert res["As_req"] > 0
    assert "H" in res["reinforcement_description"]


def test_one_way_continuous_slab():
    section = SlabSection(
        h=175, cover=25, fcu=30, lx=4000, ly=4000, fy=460,
        slab_type="one-way", support_condition="continuous"
    )
    n = 10e-3
    res = calculate_slab_reinforcement(section, n)
    assert res["status"] == "OK"
    assert "first_interior_hogging" in res["design_moments_kNm"]


def test_one_way_deflection_fail():
    section = SlabSection(
        h=100, cover=25, fcu=30, lx=6000, ly=6000, fy=460,
        slab_type="one-way", support_condition="simple",
        bar_dia=10,
    )
    n = 5e-3
    res = calculate_slab_reinforcement(section, n)
    # Very shallow slab over 6m span must fail deflection
    assert res["status"] == "Deflection Failure"


# ===========================================================================
# Two-way slab design tests
# ===========================================================================

def test_two_way_interior_panel():
    section = SlabSection(
        h=175, cover=25, fcu=30, lx=4500, ly=6000, fy=460,
        slab_type="two-way", panel_type="interior",
        support_condition="continuous"
    )
    n = 10e-3
    res = calculate_slab_reinforcement(section, n)
    assert res["status"] == "OK"
    assert "short_span_steel" in res
    assert "long_span_steel"  in res
    assert "corner_torsion_steel" in res
    assert res["corner_torsion_extent_mm"] == pytest.approx(4500 / 5, abs=1)


def test_two_way_four_discontinuous():
    section = SlabSection(
        h=200, cover=25, fcu=35, lx=4000, ly=5000, fy=460,
        slab_type="two-way", panel_type="four_discontinuous",
        support_condition="simple"
    )
    n = 9e-3
    res = calculate_slab_reinforcement(section, n)
    assert res["status"] in ("OK", "Deflection Failure")
    assert res["design_moments_kNm"]["Msx_sagging"] > 0


def test_two_way_ly_lx_too_large():
    section = SlabSection(
        h=200, cover=25, fcu=30, lx=3000, ly=7000, fy=460,
        slab_type="two-way", panel_type="interior",
    )
    n = 8e-3
    res = calculate_slab_reinforcement(section, n)
    assert res["status"] == "Use one-way design"

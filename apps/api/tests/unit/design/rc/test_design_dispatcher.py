"""
Tests for the RC design dispatcher (``core.design.rc.design_member``).

Focus: every member type that the dispatcher claims to support must route to a
real design routine and return an engineering result — never a ``skipped``
stub. This guards the EC2 column/slab/wall/staircase and BS8110 wall/staircase
branches that were previously unreachable.
"""
import pytest

from core.design.rc import design_member


def _analysis(member_type, **stress):
    """Build a minimal analysis_result with the given stress resultants."""
    sr = {
        "M_max_sagging_kNm": 80.0,
        "M_max_hogging_kNm": 40.0,
        "V_max_kN": 60.0,
        "N_axial_kN": 800.0,
    }
    sr.update(stress)
    return {"member_id": f"{member_type}-1", "member_type": member_type, "stress_resultants": sr}


# Member type -> geometry_meta needed to build a valid section
_META = {
    "beam": {"b_mm": 300, "h_mm": 500},
    "column": {"b_mm": 400, "h_mm": 400},
    "slab": {"h_mm": 200, "lx_mm": 4000, "ly_mm": 5000},
    "footing": {"b_mm": 400, "h_mm": 400, "N_uls": 800.0},
    "wall": {"b_mm": 200, "l_w_mm": 3000},
    "staircase": {"waist_mm": 200, "num_steps": 12, "span_mm": 3000},
}


@pytest.mark.parametrize("code", ["BS8110", "EC2"])
@pytest.mark.parametrize("member_type", ["beam", "column", "slab", "footing", "wall", "staircase"])
def test_dispatcher_routes_every_member_type(code, member_type):
    """No supported member type should fall through to the 'skipped' branch."""
    meta = dict(_META[member_type], member_type=member_type)
    result = design_member(_analysis(member_type), meta, design_code=code)

    assert result["member_type"] == member_type
    assert result["design_code"] == code
    # The defining property of the old gap: status == "skipped". It must be gone.
    assert result.get("status") != "skipped", (
        f"{code} {member_type} fell through to the skipped stub"
    )


def test_ec2_column_returns_required_steel():
    """EC2 column branch performs a real interaction design (As_req populated)."""
    result = design_member(
        _analysis("column", M_max_sagging_kNm=40.0, M_max_hogging_kNm=0.0,
                  V_max_kN=30.0, N_axial_kN=1500.0),
        {"member_type": "column", "b_mm": 400, "h_mm": 400},
        design_code="EC2",
    )
    assert result["As_req"] > 0
    assert result["reinforcement_description"] != "None"


def test_ec2_wall_produces_vertical_and_horizontal_steel():
    """EC2 wall branch returns both reinforcement directions."""
    result = design_member(
        _analysis("wall", N_axial_kN=1200.0),
        {"member_type": "wall", "b_mm": 200, "l_w_mm": 3000},
        design_code="EC2",
    )
    assert result["vertical_steel"] != ""
    assert result["horizontal_steel"] != ""


def test_unknown_member_type_still_skipped():
    """A genuinely unsupported type should remain a graceful skip, not raise."""
    result = design_member(
        {"member_id": "x-1", "member_type": "truss", "stress_resultants": {}},
        {"member_type": "truss"},
        design_code="EC2",
    )
    assert result["status"] == "skipped"

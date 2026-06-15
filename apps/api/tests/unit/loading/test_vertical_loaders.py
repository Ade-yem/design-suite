"""
tests/unit/loading/test_vertical_loaders.py
===========================================
Unit tests for the vertical load accumulation and reduction assemblies for columns and walls.
"""

from __future__ import annotations

import pytest
from core.loading.vertical_loaders import ColumnLoadAssembler, WallLoadAssembler
from models.loading.schema import DesignCode


def test_wall_self_weight_happy_path() -> None:
    """
    Test standard RC wall self weight calculation.
    A 200mm thick wall, 3.0m high, 1.0m long.
    RC weight density = 25.0 kN/m3.
    Self weight = 0.2m * 3.0m * 1.0m * 25.0 kN/m3 = 15.0 kN.
    """
    sw = WallLoadAssembler.calculate_self_weight(
        thickness_mm=200.0,
        height_m=3.0,
        length_m=1.0
    )
    assert pytest.approx(sw, abs=0.01) == 15.0


def test_assemble_wall_load_single_storey_happy_path() -> None:
    """
    Test load assembly for a single storey wall (no live load reduction).
    Incoming Gk = 10 kN/m, Qk = 5 kN/m.
    Wall: 200mm thick, 3.0m high. Self weight = 15.0 kN/m.
    Total Gk = 10 + 15 = 25 kN/m.
    Under BS8110:
      ULS load = 1.4 * Gk + 1.6 * Qk = 1.4 * 25 + 1.6 * 5 = 35 + 8 = 43 kN/m.
    Under EC2:
      ULS load = 1.35 * Gk + 1.5 * Qk = 1.35 * 25 + 1.5 * 5 = 33.75 + 7.5 = 41.25 kN/m.
    """
    # BS 8110
    res_bs = WallLoadAssembler.assemble_wall_load(
        incoming_gk_m=10.0,
        incoming_qk_m=5.0,
        thickness_mm=200.0,
        height_m=3.0,
        code=DesignCode.BS8110,
        num_floors_supported=1
    )
    assert res_bs["total_gk_m"] == 25.0
    assert res_bs["total_qk_m"] == 5.0
    assert res_bs["uls_axial_load_m"] == 43.0
    assert res_bs["reduction_factor"] == 1.0

    # Eurocode 2
    res_ec = WallLoadAssembler.assemble_wall_load(
        incoming_gk_m=10.0,
        incoming_qk_m=5.0,
        thickness_mm=200.0,
        height_m=3.0,
        code=DesignCode.EC2,
        num_floors_supported=1
    )
    assert res_ec["total_gk_m"] == 25.0
    assert res_ec["total_qk_m"] == 5.0
    assert res_ec["uls_axial_load_m"] == 41.25
    assert res_ec["reduction_factor"] == 1.0


def test_assemble_wall_load_multi_storey_happy_path() -> None:
    """
    Test load assembly for multi-storey wall.
    - 3 storeys: reduction factor alpha = 0.8
      Incoming Gk = 20 kN/m, Qk = 10 kN/m.
      Self-weight = 15 kN/m.
      Total Gk = 35 kN/m.
      Reduced Qk = 10 * 0.8 = 8 kN/m.
      BS 8110 ULS = 1.4 * 35 + 1.6 * 8 = 49 + 12.8 = 61.8 kN/m.
    """
    res = WallLoadAssembler.assemble_wall_load(
        incoming_gk_m=20.0,
        incoming_qk_m=10.0,
        thickness_mm=200.0,
        height_m=3.0,
        code=DesignCode.BS8110,
        num_floors_supported=3
    )
    assert res["total_gk_m"] == 35.0
    assert res["total_qk_m"] == 8.0
    assert res["uls_axial_load_m"] == 61.8
    assert res["reduction_factor"] == 0.8


def test_edge_case_zero_thickness() -> None:
    """Edge Case 1: Zero/negative thickness raises ValueError."""
    with pytest.raises(ValueError, match="Wall thickness must be positive"):
        WallLoadAssembler.calculate_self_weight(thickness_mm=0.0, height_m=3.0)
    with pytest.raises(ValueError, match="Wall thickness must be positive"):
        WallLoadAssembler.calculate_self_weight(thickness_mm=-100.0, height_m=3.0)


def test_edge_case_zero_height() -> None:
    """Edge Case 2: Zero/negative height raises ValueError."""
    with pytest.raises(ValueError, match="Wall height must be positive"):
        WallLoadAssembler.calculate_self_weight(thickness_mm=200.0, height_m=0.0)
    with pytest.raises(ValueError, match="Wall height must be positive"):
        WallLoadAssembler.calculate_self_weight(thickness_mm=200.0, height_m=-3.0)


def test_edge_case_negative_floors() -> None:
    """Edge Case 3: Supported floor count < 1 raises ValueError."""
    with pytest.raises(ValueError, match="Number of supported floors must be >= 1"):
        WallLoadAssembler.assemble_wall_load(
            incoming_gk_m=10.0,
            incoming_qk_m=5.0,
            thickness_mm=200.0,
            height_m=3.0,
            code=DesignCode.BS8110,
            num_floors_supported=0
        )


def test_edge_case_negative_loads() -> None:
    """Edge Case 4: Negative incoming load values raise ValueError."""
    with pytest.raises(ValueError, match="Incoming dead load .* cannot be negative"):
        WallLoadAssembler.assemble_wall_load(
            incoming_gk_m=-1.0,
            incoming_qk_m=5.0,
            thickness_mm=200.0,
            height_m=3.0,
            code=DesignCode.BS8110
        )
    with pytest.raises(ValueError, match="Incoming live load .* cannot be negative"):
        WallLoadAssembler.assemble_wall_load(
            incoming_gk_m=10.0,
            incoming_qk_m=-5.0,
            thickness_mm=200.0,
            height_m=3.0,
            code=DesignCode.BS8110
        )


def test_edge_case_cap_minimum_reduction() -> None:
    """Edge Case 5: 10 floors supported uses capped minimum reduction factor of 0.5."""
    res = WallLoadAssembler.assemble_wall_load(
        incoming_gk_m=10.0,
        incoming_qk_m=10.0,
        thickness_mm=200.0,
        height_m=3.0,
        code=DesignCode.BS8110,
        num_floors_supported=10
    )
    assert res["reduction_factor"] == 0.5
    assert res["total_qk_m"] == 5.0 # 10.0 * 0.5


def test_edge_case_eccentricity_moment() -> None:
    """Edge Case 6: Nominal eccentricity moment calculation."""
    # ULS Axial load = 43 kN/m (same as single storey test)
    # Eccentricity = 20mm (0.02m)
    # Expected moment = 43 * 0.02 = 0.86 kNm/m
    res = WallLoadAssembler.assemble_wall_load(
        incoming_gk_m=10.0,
        incoming_qk_m=5.0,
        thickness_mm=200.0,
        height_m=3.0,
        code=DesignCode.BS8110,
        eccentricity_mm=20.0
    )
    assert res["eccentric_moment_uls"] == 0.86

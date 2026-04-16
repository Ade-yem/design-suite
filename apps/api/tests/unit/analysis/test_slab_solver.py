import pytest
from services.analysis.slab_solver import TwoWaySlabSolver, FlatSlabSolver, RibbedSlabSolver

def test_two_way_slab_moments():
    """Verify coefficient-based moment calculation for 2-way solid slabs."""
    # 4m x 5m panel
    solver = TwoWaySlabSolver("SL1", 4.0, 5.0, ["C", "C", "C", "C"])
    # alpha_sx = 0.042, n = 10kpa -> Msx = 0.042 * 10 * 4^2 = 6.72
    result = solver.solve(10.0)
    
    assert pytest.approx(result.critical_sections["sagging"]["Msx"], abs=0.01) == 6.72
    assert "two_way_solid" in result.flags

def test_flat_slab_punching_shear():
    """Verify u1 perimeter and shear stress for flat slabs."""
    # 300x300 column, 250 thick slab, 195 d_eff
    solver = FlatSlabSolver("C1", 300, 300, 250, 35) # d approx 195
    # EC2 u1 = 2(300+300) + 4*pi*195 = 1200 + 2450.44 = 3650.44 mm
    # vEd = VEd / (u1*d)
    V_Ed = 500.0 # kN
    analysis_data = solver.check_punching_shear(V_Ed, design_code="EC2")
    
    ps = analysis_data["punching_shear"]
    assert pytest.approx(ps["control_perimeter_mm"], abs=1.0) == 3650.44
    assert ps["flag"] == "punching_shear_check_required"

def test_ribbed_slab_rib_forces():
    """Verify load per rib calculation."""
    # 600 spacing, 5m span, 10kPa load -> w_rib = 10 * 0.6 = 6 kN/m
    # M = 6 * 5^2 / 8 = 18.75 kNm
    solver = RibbedSlabSolver("RS1", 5.0, 600, 150, 50, 300)
    result = solver.solve(10.0)
    
    assert result.stress_resultants.M_max_sagging_kNm == 18.75
    assert "ribbed_slab" in result.flags

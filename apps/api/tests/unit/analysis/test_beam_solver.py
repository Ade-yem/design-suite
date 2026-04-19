import pytest
from core.analysis.beam_solver import SimplySupportedBeamSolver, MomentCoefficientSolver

def test_simply_supported_udl(simply_supported_beam):
    """Verify wL^2/8 for a 5m beam with 10kN/m load."""
    simply_supported_beam.add_udl(10.0)
    result = simply_supported_beam.solve()
    
    # M = 10 * 5^2 / 8 = 31.25
    assert result.stress_resultants.M_max_sagging_kNm == 31.25
    # V = 10 * 5 / 2 = 25.0
    assert result.stress_resultants.V_max_kN == 25.0
    # Traceability
    assert len(result.calculation_trace) > 0
    assert "M=wL²/8" in result.calculation_trace[0].formula

def test_simply_supported_point_load(simply_supported_beam):
    """Verify Pab/L for a central 50kN point load."""
    simply_supported_beam.add_point_load(50.0, 2.5) # Central
    result = simply_supported_beam.solve()
    
    # M = 50 * 5 / 4 = 62.5
    assert result.stress_resultants.M_max_sagging_kNm == 62.5
    assert result.reactions_kN[0] == 25.0

def test_moment_coefficients_bs8110():
    """Verify BS 8110 coefficients on a 3-span continuous beam."""
    solver = MomentCoefficientSolver(
        member_id="CB1",
        spans=[5.0, 5.0, 5.0],
        design_code="BS8110"
    )
    # F = n * L. Let n = 20 kN/m -> F = 100 kN.
    # End span sag = 0.090 * F * L = 0.09 * 100 * 5 = 45.0
    # First interior support hog = -0.100 * F * L = -50.0
    result = solver.solve(20.0)
    
    assert result.stress_resultants.M_max_sagging_kNm == 45.0
    assert result.stress_resultants.M_max_hogging_kNm == -50.0
    assert "BS8110 Table 3.5" in result.calculation_trace[0].clause_reference

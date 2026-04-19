import pytest
from core.analysis.column_solver import ColumnSolver

def test_column_short_classification():
    """Verify brace-factor and short column classification."""
    # 300x300 column, 3m clear height, fixed-fixed
    # Le = 0.65 * 3000 = 1950 mm
    # ratio = 1950 / 300 = 6.5 <= 15 -> Short
    solver = ColumnSolver("C1", 300, 300, 3.0, "fixed_fixed")
    result = solver.solve(1000.0, 0.0) # 1000kN axial
    
    assert "short" in result.flags
    # M_min = 1000 * max(300/20, 20)/1000 = 1000 * 20/1000 = 20 kNm
    assert result.stress_resultants.M_max_sagging_kNm == 20.0

def test_column_slender_classification():
    """Verify slender column classification and M_add."""
    # 200x200 column, 4m height, fixed-pinned
    # Le = 0.8 * 4000 = 3200 mm
    # ratio = 3200 / 200 = 16 > 15 -> Slender
    solver = ColumnSolver("C1", 200, 200, 4.0, "fixed_pinned")
    result = solver.solve(500.0, 10.0)
    
    assert "slender" in result.flags
    # Madd should be present
    assert result.stress_resultants.M_max_sagging_kNm > 10.0 # Initial + Madd + Min eccentric
    any_madd = any("Secondary moment" in step.description for step in result.calculation_trace)
    assert any_madd is True

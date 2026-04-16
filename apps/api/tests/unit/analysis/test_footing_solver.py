import pytest
from services.analysis.footing_solver import PadFootingSolver

def test_pad_footing_sizing():
    """Verify footing area sizing based on qa."""
    # N_sls = 1000 kN, qa = 200 kPa. 
    # Est SW = 10% = 100 kN. Total = 1100 kN.
    # A_req = 1100 / 200 = 5.5 m2. 
    # B = sqrt(5.5) = 2.345 -> rounded to 2.4m
    solver = PadFootingSolver("F1", 300, 300, 200)
    result = solver.solve(1000.0, 1500.0)
    
    geom = result.critical_sections["geometry"]
    assert geom["B_m"] == 2.4
    assert geom["L_m"] == 2.4

def test_pad_footing_pressure():
    """Verify bearing pressure and design moment."""
    # N_uls = 1500 kN, 2.4x2.4 footing
    # q_uls = 1500 / (2.4^2) = 1500 / 5.76 = 260.42 kPa
    # Overhang = (2.4 - 0.3) / 2 = 1.05m
    # M = 260.42 * 2.4 * 1.05^2 / 2 = 344.4 kNm
    solver = PadFootingSolver("F1", 300, 300, 200)
    result = solver.solve(1000.0, 1500.0)
    
    assert result.stress_resultants.M_max_sagging_kNm == pytest.approx(344.53, abs=0.01)
    assert result.critical_sections["pressures"]["q_uls_max"] == pytest.approx(260.42, abs=0.01)

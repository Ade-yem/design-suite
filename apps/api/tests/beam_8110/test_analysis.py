import pytest
from services.load_analysis.beam_analysis import BeamAnalysis

def test_simply_supported_udl():
    span = 6000 # mm
    w = 15 # N/mm (15 kN/m)
    beam = BeamAnalysis(span, "simple")
    beam.add_udl(w)
    res = beam.solve()
    # M_max = wL^2/8 = 15 * 6000^2 / 8 = 15 * 36,000,000 / 8 = 67,500,000 Nmm
    # V_max = wL/2 = 15 * 6000 / 2 = 45,000 N
    assert res["M_max"] == 67500000.0
    assert res["V_max"] == 45000.0

def test_simply_supported_point_load_center():
    span = 4000
    P = 50000 # 50 kN
    a = 2000 # center
    beam = BeamAnalysis(span, "simple")
    beam.add_point_load(P, a)
    res = beam.solve()
    # M_max = PL/4 = 50000 * 4000 / 4 = 50,000,000 Nmm
    # V_max = P/2 = 25,000 N
    assert res["M_max"] == 50000000.0
    assert res["V_max"] == 25000.0

def test_simply_supported_point_load_off_center():
    span = 4000
    P = 100000 # 100 kN
    a = 1000 # 1m from left
    beam = BeamAnalysis(span, "simple")
    beam.add_point_load(P, a)
    res = beam.solve()
    # R_left = 100k * 3/4 = 75k
    # R_right = 100k * 1/4 = 25k
    # M_max = P*a*b/L = 100k * 1000 * 3000 / 4000 = 75,000,000 Nmm
    assert res["M_max"] == 75000000.0
    assert res["V_max"] == 75000.0

def test_cantilever_udl():
    span = 3000
    w = 10
    beam = BeamAnalysis(span, "cantilever")
    beam.add_udl(w)
    res = beam.solve()
    # M_max = -wL^2/2 = -10 * 3000^2 / 2 = -45,000,000 Nmm (hogging)
    assert res["M_max"] == -45000000.0
    assert res["V_max"] == 30000.0

def test_fixed_fixed_udl_approximation():
    span = 5000
    w = 20
    beam = BeamAnalysis(span, "continuous")
    beam.add_udl(w)
    res = beam.solve()
    # Midspan M = wL^2/24 = 20 * 5000^2 / 24 = 20,833,333
    # Support M = -wL^2/12 = -20 * 5000^2 / 12 = -41,666,667
    # Solver picks max abs(M) and keeps the sign = -41,666,666.67
    assert pytest.approx(res["M_max"], 0.01) == -41666666.67
    assert res["V_max"] == 50000.0

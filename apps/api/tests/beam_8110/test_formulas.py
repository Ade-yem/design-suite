import math
import pytest
from core.design.rc.bs8110.formulas import (
    calculate_k,
    calculate_k_prime,
    calculate_lever_arm,
    calculate_singly_reinforced_section,
    calculate_doubly_reinforced_section,
    calculate_vc,
    apply_shear_enhancement,
    check_torsion_stress,
    calculate_anchorage_length,
)

def test_calculate_k():
    # M = 100 kNm, fcu = 30, b = 250, d = 450
    M = 100e6 
    fcu = 30
    b = 250
    d = 450
    res = calculate_k(M, fcu, b, d)
    expected_k = M / (fcu * b * d**2)
    assert pytest.approx(res["value"], 0.0001) == expected_k
    assert "BS 8110" in res["note"]

def test_calculate_k_prime_no_redistribution():
    res = calculate_k_prime(beta_b=1.0)
    assert res["value"] == 0.156
    assert res["beta_b"] == 1.0

def test_calculate_k_prime_max_redistribution():
    res = calculate_k_prime(beta_b=0.7)
    assert res["value"] == 0.1044 # 0.402 * (0.3) - 0.18 * (0.3)^2 = 0.1206 - 0.0162 = 0.1044
    assert res["beta_b"] == 0.7

def test_calculate_lever_arm():
    d = 500
    K = 0.10
    res = calculate_lever_arm(d, K)
    # z = d * [0.5 + sqrt(0.25 - K/0.9)]
    # z = 500 * [0.5 + sqrt(0.25 - 0.1111)] = 500 * [0.5 + sqrt(0.1388)] = 500 * [0.5 + 0.3726] = 436.3
    assert pytest.approx(res["value"], 0.1) == 436.3
    # z <= 0.95d = 475.
    
    K_low = 0.02
    res_low = calculate_lever_arm(d, K_low)
    assert res_low["value"] == 0.95 * d # capped

def test_calculate_doubly_reinforced_section_stress_yield():
    # Test if compression steel yields when d' is small
    M = 400e6 # Increased so M > Mu (292.5 kNm)
    fcu = 25
    fy = 460
    b = 300
    d = 500
    d_prime = 50
    K_prime = 0.156
    res = calculate_doubly_reinforced_section(M, fcu, fy, b, d, d_prime, K_prime)
    # x = (1.0 - 0.4) * 500 = 300 mm
    # 700 * (300 - 50) / 300 = 700 * 250 / 300 = 583.3 N/mm2.
    # Yield = 0.95 * 460 = 437. So it yields.
    assert "As_req" in res
    assert res["As_prime_req"] > 0

def test_calculate_vc():
    As_prov = 1000
    b = 300
    d = 500
    fcu = 30
    res = calculate_vc(As_prov, b, d, fcu)
    # pt = 100 * 1000 / (300 * 500) = 0.667%
    # vc = (0.79/1.5) * (0.667)^(1/3) * (1.0) * (30/25)^(1/3)
    # vc = 0.526 * 0.874 * 1.0 * 1.062 = 0.488
    assert pytest.approx(res["value"], 0.01) == 0.488

def test_shear_enhancement():
    vc = 0.50
    d = 500
    av = 400 # av < 2d
    res = apply_shear_enhancement(vc, av, d)
    # factor = 1000 / 400 = 2.5
    # vc_enh = 2.5 * 0.5 = 1.25
    assert res["value"] == 1.25
    
    res_no_enh = apply_shear_enhancement(vc, 1200, d) # av > 2d
    assert res_no_enh["value"] == vc

def test_check_torsion_stress():
    T = 20e6 # Nmm
    h = 500
    b = 300
    fcu = 30
    res = check_torsion_stress(T, h, b, fcu)
    # vt = 2T / (b^2 * (h - b/3)) = 2 * 20e6 / (300^2 * (500 - 100)) = 40e6 / (90000 * 400) = 40e6 / 36e6 = 1.11 N/mm2
    assert pytest.approx(res["vt"], 0.01) == 1.11
    assert res["status"] == "REINFORCE" # vt > 0.37 (for C30)

def test_calculate_anchorage_length():
    phi = 20
    fcu = 40
    fy = 460
    # beta = 0.50 for tension deformed
    res = calculate_anchorage_length(phi, fcu, fy, bar_type="deformed", condition="tension")
    # fbu = 0.5 * sqrt(40) = 3.16 N/mm2
    # L = (0.95 * 460 * 20) / (4 * 3.16) = 8740 / 12.64 = 691 mm
    assert pytest.approx(res["length"], 5) == 691

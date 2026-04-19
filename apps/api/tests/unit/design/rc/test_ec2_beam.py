import pytest
from models.ec2.beam import EC2BeamSection
from core.design.rc.eurocode2.beam import calculate_beam_reinforcement

def test_ec2_beam_singly_reinforced():
    """Verify EC2 beam design for a standard singly-reinforced section."""
    # 300x600 section, C30/37, 30mm cover, H8 links, H20 bars
    # d = 600 - 30 - 8 - 10 = 552 mm
    section = EC2BeamSection(
        b=300, h=600, cover=30, fck=30, fyk=500
    )
    
    # Design moment 200 kNm = 200e6 Nmm
    # K = 200e6 / (300 * 552^2 * 30) = 0.073 < 0.167 (OK)
    # z = 552 * [0.5 + sqrt(0.25 - 0.073/1.134)] = 552 * 0.93 = 513 mm
    # As = 200e6 / (0.87 * 500 * 513) = 200e6 / 223155 = 896 mm2
    results = calculate_beam_reinforcement(
        section=section,
        M=200e6,
        V=100e3,
        span=6000
    )
    
    assert results["status"] == "OK"
    assert results["As_req"] == pytest.approx(923.4, abs=0.1)
    assert results["As_prov"] >= results["As_req"]
    assert "3H20" in results["reinforcement_description"] # 3x314 = 942 mm2

def test_ec2_beam_shear_links():
    """Verify shear link calculation."""
    section = EC2BeamSection(b=300, h=600, cover=30, fck=30)
    # High shear force 400kN -> requires links
    results = calculate_beam_reinforcement(
        section=section,
        M=100e6,
        V=400e3,
        span=6000
    )
    
    assert results["status"] == "OK"
    assert results["shear_links_Asw_s"] > 0.5 # mm2/mm
    assert "Asw/s" in results["shear_links_description"]

def test_ec2_beam_deflection_fail():
    """Verify deflection failure for shallow beam on long span."""
    # 250mm deep beam, 8m span -> L/d = 8000/200 = 40 (Very high)
    section = EC2BeamSection(b=300, h=250, cover=25, fck=30)
    results = calculate_beam_reinforcement(
        section=section,
        M=50e6,
        V=20e3,
        span=8000
    )
    
    assert results["deflection_check"] == "FAIL"
    assert "Deflection Failure" in results["status"]

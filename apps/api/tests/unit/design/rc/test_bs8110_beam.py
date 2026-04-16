import pytest
from models.bs8110.beam import BeamSection
from services.design.rc.bs8110.beam import calculate_beam_reinforcement

def test_bs8110_beam_singly_reinforced():
    """Verify BS 8110 beam design for a standard singly-reinforced section."""
    # 225x450 section, C30, 25mm cover, H8 links, H20 bars
    # d = 450 - 25 - 8 - 10 = 407 mm
    section = BeamSection(
        b=225, h=450, cover=25, fcu=30, fy=460, fyv=250
    )
    
    # Design moment 100 kNm = 100e6 Nmm
    # K = 100e6 / (225 * 407^2 * 30) = 0.089 < 0.156 (OK)
    # z = d * [0.5 + sqrt(0.25 - 0.089/0.9)] = 407 * 0.88 = 360 mm
    # As = 100e6 / (0.87 * 460 * 360) = 100e6 / 144072 = 694 mm2
    results = calculate_beam_reinforcement(
        section=section,
        M=100e6,
        V=50e3,
        span=5000
    )
    
    assert results["status"] == "OK"
    assert results["As_req"] == pytest.approx(663.7, abs=1.0)
    assert results["As_prov"] >= results["As_req"]
    assert results["reinforcement_description"] != "None"

def test_bs8110_beam_shear_failure():
    """Verify shear stress limit failure (max 0.8*sqrt(fcu) or 5N/mm2)."""
    # 150x150 beam, 300kN shear -> v = 300000 / (150 * 107) = 18.6 N/mm2 (Extremely high)
    section = BeamSection(b=150, h=150, cover=25, fcu=30, fy=460, fyv=250)
    results = calculate_beam_reinforcement(
        section=section,
        M=10e6,
        V=350e3,
        span=2000
    )
    
    assert results["status"] == "Shear Failure"
    assert any("v_max" in note for note in results["notes"])

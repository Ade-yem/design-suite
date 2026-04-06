from models.beam import BeamSection
from services.calculations.bs8110.beam import calculate_beam_reinforcement

def test_rectangular_beam_singly_reinforced():
    section = BeamSection(
        b=250, h=500, cover=25, fcu=30, fy=460, fyv=250,
        section_type="rectangular", support_condition="simple"
    )
    M = 100e6 # Nmm
    V = 50e3 # N -> 50 kN
    span = 6000
    res = calculate_beam_reinforcement(section, M, V, span)
    assert res["status"] == "OK"
    assert res["As_req"] > 0
    assert res["As_prov"] >= res["As_req"]
    assert "H" in res["reinforcement_description"]

def test_flanged_beam_sagging():
    section = BeamSection(
        b=250, h=500, cover=25, fcu=30, fy=460, fyv=250,
        section_type="flanged", support_condition="simple",
        bf=1000, hf=150
    )
    M = 200e6 
    V = 80e3
    span = 6000
    res = calculate_beam_reinforcement(section, M, V, span)
    
    assert res["status"] == "OK"
    # Should use the flange width bf=1000 for compression
    assert "flange" in "".join(res["notes"]).lower()

def test_flanged_beam_hogging():
    # Negative moment (hogging) at support. Should treat as rectangular.
    section = BeamSection(
        b=250, h=500, cover=25, fcu=30, fy=460, fyv=250,
        section_type="flanged", support_condition="continuous",
        bf=1000, hf=150
    )
    M = -150e6 
    V = 100e3
    span = 6000
    res = calculate_beam_reinforcement(section, M, V, span)
    
    assert res["status"] == "OK"
    assert "Hogging" in "".join(res["notes"])
    assert "rectangular" in "".join(res["notes"]).lower()

def test_iterative_depth_two_layers():
    # Force a lot of reinforcement to trigger 2 layers
    section = BeamSection(
        b=150, h=400, cover=25, fcu=30, fy=460, fyv=250,
        section_type="rectangular", support_condition="simple"
    )
    M = 160e6 # High moment for a small section
    V = 50e3
    span = 4000
    res = calculate_beam_reinforcement(section, M, V, span)
    
    # Check if notes contain iteration mentions or layer mentions
    notes_str = "".join(res["notes"])
    assert "Iteration 2" in notes_str or "Two layers" in notes_str

def test_deep_beam_side_bars():
    section = BeamSection(
        b=300, h=800, cover=30, fcu=30, fy=460, fyv=250,
        section_type="rectangular", support_condition="simple"
    )
    M = 100e6
    V = 50e3
    span = 4000
    res = calculate_beam_reinforcement(section, M, V, span)
    
    assert any("side reinforcement" in n.lower() for n in res["notes"])

def test_shear_failure():
    section = BeamSection(
        b=150, h=300, cover=25, fcu=25, fy=460, fyv=250,
        section_type="rectangular", support_condition="simple"
    )
    M = 20e6
    V = 500e3 # Extreme shear force
    span = 3000
    res = calculate_beam_reinforcement(section, M, V, span)
    
    assert res["status"] == "Shear Failure"

def test_deflection_failure():
    # Very long span, shallow beam
    section = BeamSection(
        b=250, h=300, cover=25, fcu=30, fy=460, fyv=250,
        section_type="rectangular", support_condition="simple"
    )
    M = 50e6
    V = 20e3
    span = 12000 # 12 meters is way too much for a 300mm beam
    res = calculate_beam_reinforcement(section, M, V, span)
    
    assert res["status"] == "Deflection Failure"


import pytest
from models.bs8110.slab import SlabSection
from services.design.rc.bs8110.slab import calculate_slab_reinforcement

def test_slab_design_basic():
    # 150mm thick slab, 1m strip
    section = SlabSection(
        h=150, cover=25, fcu=30, fy=460, bar_dia=10, 
        support_condition="simple", lx=3000, ly=4000
    )
    M = 15e6  # 15 kNm
    V = 20e3  # 20 kN
    span = 3000
    
    res = calculate_slab_reinforcement(section, M, V, span)
    
    assert res["status"] == "OK"
    assert res["As_req"] > 0
    assert res["As_prov"] >= res["As_req"]
    assert "H" in res["reinforcement_description"]
    assert "@" in res["reinforcement_description"]

def test_slab_deflection_failure():
    # Very long span, shallow slab
    section = SlabSection(
        h=150, cover=25, fcu=30, fy=460, bar_dia=10, 
        support_condition="simple", lx=3000, ly=4000
    )
    M = 10e6
    V = 10e3
    span = 8000 # 8 meters for a 150mm simple slab will fail
    
    res = calculate_slab_reinforcement(section, M, V, span)
    assert res["status"] == "Deflection Failure"

def test_slab_shear_failure():
    section = SlabSection(
        h=150, cover=25, fcu=30, fy=460, bar_dia=10, 
        support_condition="simple", lx=3000, ly=4000
    )
    M = 10e6
    V = 300e3 # Extreme shear
    span = 4000
    
    res = calculate_slab_reinforcement(section, M, V, span)
    assert res["status"] == "Shear Failure"

def test_slab_reinforcement_limits():
    # High moment -> high K -> inadequate section
    section = SlabSection(
        h=120, cover=25, fcu=30, fy=460, bar_dia=10, 
        support_condition="simple", lx=3000, ly=4000
    )
    M = 100e6 # Extreme moment for 120mm slab
    V = 10e3
    span = 3000
    
    res = calculate_slab_reinforcement(section, M, V, span)
    assert res["status"] == "Section Inadequate"

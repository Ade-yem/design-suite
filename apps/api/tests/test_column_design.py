import pytest
from models.bs8110.column import ColumnSection
from core.design.rc.bs8110.column import calculate_column_reinforcement

def test_short_column_axial():
    # 300x300 column, 3m tall
    section = ColumnSection(
        b=300, h=300, l_ex=3000, l_ey=3000,
        cover=35, fcu=30, fy=460, braced=True
    )
    N = 1000e3  # 1000 kN
    M = 10e6    # 10 kNm (very small)
    
    res = calculate_column_reinforcement(section, N, M)
    
    assert res["status"] == "OK"
    assert res["slenderness"] == "Short"
    assert res["As_req"] > 0
    assert res["As_prov"] >= res["As_req"]
    assert "H" in res["reinforcement_description"]

def test_slender_column():
    # 200x200 column, 4m tall -> slenderness = 20
    section = ColumnSection(
        b=200, h=200, l_ex=4000, l_ey=4000,
        cover=25, fcu=30, fy=460, braced=True
    )
    N = 500e3
    M = 5e6
    
    res = calculate_column_reinforcement(section, N, M)
    
    assert res["status"] == "OK"
    assert res["slenderness"] == "Slender"
    assert "add" in "".join(res["notes"]).lower()

def test_column_inadequate():
    section = ColumnSection(
        b=200, h=200, l_ex=3000, l_ey=3000,
        cover=35, fcu=30, fy=460, braced=True
    )
    # Huge load for a 200x200 column
    N = 5000e3
    M = 200e6
    
    res = calculate_column_reinforcement(section, N, M)
    
    assert res["status"] == "Section Inadequate"

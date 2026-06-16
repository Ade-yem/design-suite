"""
Staircase drawing generator (Workstream B, Slice 3c).

The generator used to be a stub returning empty lists. It now produces a real
flight drawing: a transverse waist section and a longitudinal elevation (tread/
riser profile + inclined waist + main bars + landing).
"""
from core.drawing.staircase import StaircaseDrawingGenerator


def _member(num_steps=18, **geo):
    geometry = {"waist": 150, "riser": 171, "going": 258, "span": 5642,
                "num_steps": num_steps, "width": 1200, **geo}
    return {
        "member_id": "ST1",
        "design_code": "BS8110",
        "geometry": geometry,
        "design": {"cover_mm": 25, "fcu_MPa": 30},
        "reinforcement": {
            "main_bars": [{"diameter": 12, "spacing": 150, "mark": "S1"}],
            "distribution_bars": [{"diameter": 10, "spacing": 250, "mark": "S2"}],
        },
    }


def test_all_views_are_non_empty():
    g = StaircaseDrawingGenerator(_member())
    assert g.draw_section()
    assert g.draw_elevation()
    assert g.draw_dimensions()
    assert g.draw_bar_marks()
    assert g.draw_annotations()


def test_elevation_draws_each_tread_and_riser():
    n = 12
    g = StaircaseDrawingGenerator(_member(num_steps=n))
    elev = g.draw_elevation()
    # n treads + n risers + waist soffit + main bars + landing rect.
    assert len(elev) == 2 * n + 3
    assert any(c["type"] == "rect" for c in elev)  # landing
    assert any(c["type"] == "line" and c["style"] == "rebar" for c in elev)  # main bars


def test_section_places_main_bars_as_circles():
    g = StaircaseDrawingGenerator(_member())
    sec = g.draw_section()
    assert any(c["type"] == "circle" and c["style"] == "rebar" for c in sec)


def test_renders_with_defaults_when_geometry_absent():
    g = StaircaseDrawingGenerator({"member_id": "ST2"})
    assert g.draw_section()
    assert g.draw_elevation()
    assert g.canvas_bounds()["width"] >= 500


def test_canvas_bounds_grow_with_flight():
    small = StaircaseDrawingGenerator(_member(num_steps=8))
    big = StaircaseDrawingGenerator(_member(num_steps=24))
    assert big.canvas_bounds()["height"] > small.canvas_bounds()["height"]

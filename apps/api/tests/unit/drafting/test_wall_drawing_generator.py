"""
Wall drawing generator tests.

The generator used to be a stub returning empty lists.  It now produces a real
RC wall detail (horizontal section + face elevation) from the flat
``design_member`` output (``vertical_steel`` / ``horizontal_steel`` strings),
reading section dimensions defensively with fallbacks.
"""
from core.drawing import generate_drawing_commands
from core.drawing.wall import WallDrawingGenerator

_PAD = 50


def _member(**overrides):
    member = {
        "member_id": "W1",
        "member_type": "wall",
        "design_code": "BS8110",
        "vertical_steel": "H12 @ 150 c/c",
        "horizontal_steel": "H10 @ 250 c/c",
        "slenderness": "Stocky",
        "fcu_MPa": 30,
        "fy_MPa": 500,
        "meta": {"h_wall_mm": 200, "l_w_mm": 3000, "l_e_mm": 3000, "cover_mm": 25},
    }
    member.update(overrides)
    return member


def test_all_views_are_non_empty():
    g = WallDrawingGenerator(_member())
    assert g.draw_section()
    assert g.draw_elevation()
    assert g.draw_dimensions()
    assert g.draw_bar_marks()
    assert g.draw_annotations()


def test_section_places_vertical_bars_as_rebar_circles():
    g = WallDrawingGenerator(_member())
    sec = g.draw_section()
    bars = [c for c in sec if c.get("type") == "circle" and c.get("style") == "rebar"]
    assert bars  # vertical bars drawn on both faces


def test_bars_within_cover_bounds():
    g = WallDrawingGenerator(_member())
    sec = g.draw_section()
    strip = min(g.l_w, 1000.0)
    r = g.vert_spec["diameter"] / 2
    min_x = _PAD + g.cover + r
    max_x = _PAD + strip - g.cover - r
    for bar in (c for c in sec if c.get("type") == "circle"):
        assert min_x - 0.01 <= bar["cx"] <= max_x + 0.01


def test_elevation_has_both_vertical_and_horizontal_bars():
    g = WallDrawingGenerator(_member())
    elev = g.draw_elevation()
    rebar = [c for c in elev if c.get("type") == "line" and c.get("style") == "rebar"]
    # vertical bars run top-to-bottom; horizontal bars run left-to-right.
    assert any(c["x1"] == c["x2"] for c in rebar)
    assert any(c["y1"] == c["y2"] for c in rebar)


def test_outline_dimensions_in_mm():
    g = WallDrawingGenerator(_member())
    elev = g.draw_elevation()
    outline = next(c for c in elev if c.get("style") == "structural_outline")
    assert outline["width"] == 3000
    assert outline["height"] == 3000


def test_required_fields_present():
    g = WallDrawingGenerator(_member())
    cmds = g.draw_section() + g.draw_elevation() + g.draw_dimensions()
    for cmd in cmds:
        assert "type" in cmd
        if cmd["type"] != "dimension":
            assert "style" in cmd


def test_renders_with_defaults_when_geometry_absent():
    g = WallDrawingGenerator({"member_id": "W2"})
    assert g.draw_section()
    assert g.draw_elevation()
    assert g.canvas_bounds()["width"] >= 500


def test_dispatch_via_registry():
    out = generate_drawing_commands(_member())
    assert out["section"]
    assert out["elevation"]

"""
Footing drawing generator tests.

The generator used to be a stub returning empty lists.  It now produces a real
pad-footing detail (vertical section + reinforcement plan) from the flat
``design_member`` output (``reinforcement_x`` / ``reinforcement_y`` strings),
reading section dimensions defensively with fallbacks.

Also guards the registry fix: footings dispatch under ``member_type="footing"``
(the designer's value), which previously did not match the registry key.
"""
from core.drawing import generate_drawing_commands
from core.drawing.footing import FootingDrawingGenerator

_PAD = 50


def _member(**overrides):
    member = {
        "member_id": "F1",
        "member_type": "footing",
        "design_code": "BS8110",
        "reinforcement_x": "H16 @ 150 c/c",
        "reinforcement_y": "H16 @ 175 c/c",
        "q_max_kNm2": 120.0,
        "status": "OK",
        "fcu_MPa": 30,
        "fy_MPa": 460,
        "meta": {"lx": 1800, "ly": 1800, "h_footing_mm": 500, "c1": 300, "c2": 300, "cover_mm": 50},
    }
    member.update(overrides)
    return member


def test_all_views_are_non_empty():
    g = FootingDrawingGenerator(_member())
    assert g.draw_section()
    assert g.draw_elevation()
    assert g.draw_dimensions()
    assert g.draw_bar_marks()
    assert g.draw_annotations()


def test_section_places_bottom_bars_as_rebar_circles():
    g = FootingDrawingGenerator(_member())
    sec = g.draw_section()
    bars = [c for c in sec if c.get("type") == "circle" and c.get("style") == "rebar"]
    assert bars


def test_bars_within_cover_bounds():
    g = FootingDrawingGenerator(_member())
    sec = g.draw_section()
    r = g.x_spec["diameter"] / 2
    min_x = _PAD + g.cover + r
    max_x = _PAD + g.lx - g.cover - r
    for bar in (c for c in sec if c.get("type") == "circle"):
        assert min_x - 0.01 <= bar["cx"] <= max_x + 0.01


def test_plan_has_both_x_and_y_bars():
    g = FootingDrawingGenerator(_member())
    plan = g.draw_elevation()
    rebar = [c for c in plan if c.get("type") == "line" and c.get("style") == "rebar"]
    # x bars run horizontally (y1 == y2); y bars run vertically (x1 == x2).
    assert any(c["y1"] == c["y2"] for c in rebar)
    assert any(c["x1"] == c["x2"] for c in rebar)


def test_outline_dimensions_in_mm():
    g = FootingDrawingGenerator(_member())
    plan = g.draw_elevation()
    outline = next(c for c in plan if c.get("style") == "structural_outline")
    assert outline["width"] == 1800
    assert outline["height"] == 1800


def test_required_fields_present():
    g = FootingDrawingGenerator(_member())
    cmds = g.draw_section() + g.draw_elevation() + g.draw_dimensions()
    for cmd in cmds:
        assert "type" in cmd
        if cmd["type"] != "dimension":
            assert "style" in cmd


def test_renders_with_defaults_when_geometry_absent():
    g = FootingDrawingGenerator({"member_id": "F2"})
    assert g.draw_section()
    assert g.draw_elevation()
    assert g.canvas_bounds()["width"] >= 500


def test_dispatch_via_registry_member_type_footing():
    # The designer sets member_type="footing"; this must dispatch (registry fix).
    out = generate_drawing_commands(_member())
    assert out["section"]
    assert out["elevation"]

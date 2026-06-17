"""
Unit tests for the reinforcement-spec parser used by the wall and footing
drawing generators.
"""
from core.drawing.rebar_spec import bar_count_for_width, parse_bar_spec


def test_parses_standard_h_at_spacing():
    spec = parse_bar_spec("H12 @ 150 c/c")
    assert spec["diameter"] == 12
    assert spec["spacing"] == 150
    assert spec["count"] is None


def test_parses_alternate_diameter_and_spacing():
    spec = parse_bar_spec("H16 @ 175 c/c")
    assert spec["diameter"] == 16
    assert spec["spacing"] == 175


def test_parses_optional_leading_count():
    spec = parse_bar_spec("10H16 @ 150 c/c")
    assert spec["count"] == 10
    assert spec["diameter"] == 16
    assert spec["spacing"] == 150


def test_whitespace_tolerant():
    spec = parse_bar_spec("  H10@200  ")
    assert spec["diameter"] == 10
    assert spec["spacing"] == 200


def test_empty_and_garbage_fall_back_to_defaults():
    for bad in (None, "", "None", "Provide > max spacing limits"):
        spec = parse_bar_spec(bad)
        assert spec["diameter"] == 12
        assert spec["spacing"] == 200


def test_bar_count_uses_explicit_count_when_present():
    assert bar_count_for_width({"count": 8, "spacing": None}, 1500) == 8


def test_bar_count_derives_from_spacing():
    # 1000 wide at 200 spacing → floor(1000/200)+1 = 6 bars.
    assert bar_count_for_width({"count": None, "spacing": 200}, 1000) == 6


def test_bar_count_minimum_two():
    assert bar_count_for_width({"count": None, "spacing": 5000}, 1000) == 2

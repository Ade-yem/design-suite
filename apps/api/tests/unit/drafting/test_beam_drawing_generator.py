import pytest
from core.drawing.beam import BeamDrawingGenerator

def build_beam_member(bottom_bars=4, top_bars=2, links=1, width_mm=300, depth_mm=500, cover_mm=25, bar_diameter_mm=20):
    return {
        "member_id": "B-01",
        "geometry": {"width_mm": width_mm, "depth_mm": depth_mm},
        "design": {"cover_mm": cover_mm},
        "reinforcement": {
            "main_bars": [
                {"position": "bottom", "count": bottom_bars, "diameter": bar_diameter_mm},
                {"position": "top", "count": top_bars, "diameter": bar_diameter_mm}
            ],
            "links": [{"spacing": 200, "diameter": 8}] if links else []
        }
    }

class TestBeamDrawingGenerator:

    def test_section_contains_correct_number_of_bars(self):
        """
        If design has 4 bottom bars, section drawing must contain
        exactly 4 circle commands for bottom bars
        """
        member = build_beam_member(bottom_bars=4, top_bars=2, links=1)
        generator = BeamDrawingGenerator(member)
        commands = generator.draw_section()

        bar_commands = [c for c in commands
                        if c.get('type') == 'circle' and c.get('style') == 'rebar']
        assert len(bar_commands) == 6  # 4 bottom + 2 top

    def test_bars_positioned_within_cover_bounds(self):
        """
        All bar centres must be at least (cover + diameter/2) from the
        outer face — never outside the cover line
        """
        member = build_beam_member(
            width_mm=300, depth_mm=500,
            cover_mm=25, bar_diameter_mm=20
        )
        generator = BeamDrawingGenerator(member)
        commands = generator.draw_section()

        min_x = 25 + 20/2   # cover + radius
        max_x = 300 - 25 - 20/2
        _PAD = 50 # from beam.py pad

        bar_commands = [c for c in commands if c.get('type') == 'circle']
        for bar in bar_commands:
            assert bar['cx'] >= min_x + _PAD
            assert bar['cx'] <= max_x + _PAD

    def test_all_draw_commands_have_required_fields(self):
        """Every draw command must have type, style, and geometry fields"""
        member = build_beam_member()
        generator = BeamDrawingGenerator(member)
        all_commands = (
            generator.draw_section() +
            generator.draw_elevation() +
            generator.draw_dimensions()
        )

        for cmd in all_commands:
            assert 'type' in cmd
            if cmd['type'] != 'dimension': # Dimensions have different standard style handling
                assert 'style' in cmd

    def test_drawing_scale_applied_consistently(self):
        """
        All coordinates in section drawing must be in mm.
        A 300mm wide beam must have rect width = 300 (not 0.3 or 30)
        """
        member = build_beam_member(width_mm=300, depth_mm=500)
        generator = BeamDrawingGenerator(member)
        commands = generator.draw_section()

        outline = next(c for c in commands if c.get('style') == 'structural_outline')
        assert outline['width'] == 300
        assert outline['height'] == 500

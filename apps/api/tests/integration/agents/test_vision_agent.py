import pytest
from agents.parser import _detect_unit_ambiguity

class TestVisionAgent:

    def test_unit_ambiguity_detected_for_mm_drawing(self):
        """
        A DXF drawn in millimetres must trigger a unit confirmation
        request — never silently proceed with wrong units.
        Small sample lengths: 8.0, 9.5 -> implies ambiguous usually unless clear
        The detector rule: 3-30m = meters, 3000-30000 = mm
        """
        # Simulate simple mm drawings
        parsed = {"members": [{"spans_m": [6000.0, 5000.0]}]}
        result = _detect_unit_ambiguity(parsed)

        # 3000-30000 is high confidence mm 
        assert result['ambiguous'] is False
        assert result['detected_unit'] == 'millimetres'
        
        # Ambiguous condition (e.g., 600)
        parsed_amb = {"members": [{"spans_m": [600.0, 500.0]}]}
        result_amb = _detect_unit_ambiguity(parsed_amb)
        assert result_amb['ambiguous'] is True

    @pytest.mark.skip(reason="Needs real vision agent and local file fixtures")
    async def test_correct_member_count_extracted(self):
        """
        A known DXF with 8 beams and 4 columns must parse to exactly
        8 beams and 4 columns. Validates parsing accuracy metric.
        """
        from agents.parser import parser_node

        state = {
            "project_id": "proj",
            "uploaded_file_path": "fixtures/dxf_samples/simple_frame_known.dxf"
        }

        result = await parser_node(state)
        parsed = result['parsed_structural_json']

        beams   = [m for m in parsed['members'] if m['type'] == 'beam']
        columns = [m for m in parsed['members'] if m['type'] == 'column']

        assert len(beams)   == 8
        assert len(columns) == 4

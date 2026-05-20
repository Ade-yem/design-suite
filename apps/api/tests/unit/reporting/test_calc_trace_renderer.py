import pytest
import xml.etree.ElementTree as ET
from core.reporting.calc_sheet import BMDGenerator, SFDGenerator, CalcSheetEngine
from core.reporting.normalizer import ReportProject, ReportMember


def _sample_project() -> ReportProject:
    return ReportProject(name="Test Project", reference="REF-001")


def _sample_member() -> ReportMember:
    return ReportMember(
        member_id="B-01",
        member_type="beam",
        floor_level="First Floor",
        design_code="BS8110",
        loading_output={"gk": 5.0, "qk": 3.0, "n_design": 13.8},
        analysis_output={
            "M_max_kNm": 145.8,
            "V_max_kN": 81.0,
            "span_m": 6.0,
            "bmd_points": [
                {"position_m": 0.0, "moment_kNm": 0.0},
                {"position_m": 3.0, "moment_kNm": 145.8},
                {"position_m": 6.0, "moment_kNm": 0.0},
            ],
            "sfd_points": [
                {"position_m": 0.0, "shear_kN": 81.0},
                {"position_m": 6.0, "shear_kN": -81.0},
            ],
        },
        design_output={"fcu": 30, "fy": 460, "As_req": 950.0, "As_prov": 1005.0},
        geometry={"span_m": 6.0, "b": 300, "h": 550},
        status="PASS",
    )


class TestBMDGenerator:

    def test_svg_is_valid_xml(self):
        """BMDGenerator must return well-formed SVG (parseable by stdlib ET)"""
        gen = BMDGenerator()
        svg = gen.generate({}, span_m=6.0)
        ET.fromstring(svg)  # raises xml.etree.ElementTree.ParseError if malformed

    def test_bmd_points_produce_peak_label(self):
        """Peak moment value must appear as text in the generated SVG"""
        gen = BMDGenerator()
        svg = gen.generate(_sample_member().analysis_output, span_m=6.0)
        assert "145.8" in svg

    def test_empty_analysis_output_still_returns_svg(self):
        """Calling generate with an empty dict must not raise"""
        gen = BMDGenerator()
        svg = gen.generate({}, span_m=4.0)
        assert svg.startswith("<svg")


class TestSFDGenerator:

    def test_svg_is_valid_xml(self):
        """SFDGenerator must return well-formed SVG"""
        gen = SFDGenerator()
        svg = gen.generate({}, span_m=6.0)
        ET.fromstring(svg)

    def test_empty_analysis_output_still_returns_svg(self):
        """Calling generate with an empty dict must not raise"""
        gen = SFDGenerator()
        svg = gen.generate({}, span_m=4.0)
        assert svg.startswith("<svg")


class TestCalcSheetEngine:

    def test_build_returns_all_required_keys(self):
        """build() must return all keys consumed by the Jinja2 template"""
        engine = CalcSheetEngine()
        ctx = engine.build(_sample_project(), _sample_member())

        required_keys = {
            "project", "member", "design_basis", "loading",
            "analysis", "calc_steps", "results", "bmd_svg", "sfd_svg",
        }
        assert required_keys.issubset(ctx.keys())

    def test_bmd_svg_is_embedded_in_context(self):
        """bmd_svg in context must be a non-empty SVG string"""
        engine = CalcSheetEngine()
        ctx = engine.build(_sample_project(), _sample_member())

        assert ctx["bmd_svg"].startswith("<svg")

    def test_project_and_member_are_forwarded_unchanged(self):
        """project and member in context must be the same objects passed in"""
        engine = CalcSheetEngine()
        project = _sample_project()
        member = _sample_member()
        ctx = engine.build(project, member)

        assert ctx["project"] is project
        assert ctx["member"] is member

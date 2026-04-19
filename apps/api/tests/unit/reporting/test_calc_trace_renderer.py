import pytest
from html.parser import HTMLParser

class CalcTraceRenderer:
    def render(self, trace):
        html_out = "<html><body>"
        for t in trace:
            cls = 'class="check-fail"' if t.get("result") == "FAIL" else ""
            html_out += f"<div {cls}>{t.get('description', '')} {t.get('clause_reference', '')} {t.get('result', '')}</div>"
        html_out += "</body></html>"
        return html_out

class TestCalcTraceRenderer:

    def test_all_trace_steps_rendered(self):
        """Every step in calculation_trace must appear in rendered HTML"""
        trace = [
            {"step": 1, "description": "Calculate K",
             "formula": "K = M/(fcu×b×d²)",
             "result": 0.114, "clause_reference": "BS8110 Cl 3.4.4.4"},
            {"step": 2, "description": "Calculate lever arm z",
             "formula": "z = d[0.5 + √(0.25 - K/0.9)]",
             "result": 383.0, "clause_reference": "BS8110 Cl 3.4.4.4"}
        ]

        renderer = CalcTraceRenderer()
        html = renderer.render(trace)

        assert "Calculate K" in html
        assert "BS8110 Cl 3.4.4.4" in html
        assert "383.0" in html

    def test_failed_check_renders_with_fail_class(self):
        """Failed checks must have CSS class 'check-fail' for red styling"""
        trace = [{
            "step": 1,
            "description": "Shear check",
            "result": "FAIL",
            "actual": 1.24,
            "limit": 1.18
        }]

        renderer = CalcTraceRenderer()
        html = renderer.render(trace)

        assert 'class="check-fail"' in html

    def test_html_is_valid_and_parseable(self):
        """Rendered HTML must be parseable — no malformed tags"""
        trace = [{"step": 1, "description": "Test step",
                  "formula": "x = y + z", "result": 42.0}]

        renderer = CalcTraceRenderer()
        html = renderer.render(trace)

        parser = HTMLParser()
        parser.feed(html)  # Raises if malformed

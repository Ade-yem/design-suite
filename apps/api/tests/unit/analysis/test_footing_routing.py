"""
Footing solver routing (Workstream B, Slice 2b).

The analysis engine only ever built a PadFootingSolver and returned ``None`` for
any other footing type, so the existing CombinedFootingSolver / StripFootingSolver
were unreachable. Route them by ``footing_type``, with a graceful pad fallback
when the extra (grouped) inputs aren't supplied.
"""
from core.analysis.engine import AnalysisEngine
from models.loading.schema import MemberLoadOutput


def _engine():
    return AnalysisEngine(design_code="BS8110")


def _load():
    return MemberLoadOutput(
        member_id="F-C1",
        member_type="footing",
        design_code="BS8110",
        spans=[{"span_id": "S1", "length_m": 1.0, "loads": {"n_uls": 900, "n_sls": 650}}],
        combination_used="1.4Gk+1.6Qk",
    )


def test_pad_footing_routes_to_real_result():
    res = _engine()._route_footing(_load(), {"footing_type": "pad", "qa": 200, "N_uls": 900, "N_sls": 650})
    assert res is not None
    assert res.member_type == "footing"


def test_combined_footing_routes_when_paired_inputs_present():
    meta = {
        "footing_type": "combined", "qa": 200, "N_uls": 900, "N_sls": 650,
        "neighbour_N_uls": 800, "neighbour_dist_m": 4.0, "edge_distance_m": 0.5,
    }
    res = _engine()._route_footing(_load(), meta)
    assert res is not None
    assert res.member_type == "footing"


def test_strip_footing_routes_when_strip_inputs_present():
    meta = {"footing_type": "strip", "qa": 200, "N_uls": 900, "strip_width_m": 1.2, "strip_span_m": 4.0}
    res = _engine()._route_footing(_load(), meta)
    assert res is not None
    assert res.member_type == "footing"


def test_combined_without_inputs_falls_back_to_pad_not_none():
    # The previous behaviour returned None here, dropping the footing entirely.
    res = _engine()._route_footing(_load(), {"footing_type": "combined", "qa": 200, "N_uls": 900})
    assert res is not None
    assert res.member_type == "footing"

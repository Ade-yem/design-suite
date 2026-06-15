"""Unit tests for _group_collinear_beam_runs in core.parsing.extractor."""

import math
import pytest

from core.parsing.extractor import _group_collinear_beam_runs


def make_beam(mid: str, sx: float, sy: float, ex: float, ey: float,
              b: float = 225.0, h: float = 450.0) -> dict:
    """Factory: return a beam member dict matching the extractor's output schema."""
    length_mm = math.hypot(ex - sx, ey - sy)
    l_clear = round(length_mm / 1000.0, 4)
    I_val = round((b / 1000.0) * ((h / 1000.0) ** 3) / 12.0, 6)
    return {
        "member_id": mid,
        "member_type": "beam",
        "type": "beam",
        "start_point": {"x": sx, "y": sy},
        "end_point": {"x": ex, "y": ey},
        "center_point": None,
        "boundary_polygon": None,
        "is_void": False,
        "meta": {
            "b_mm": b,
            "h_mm": h,
            "L_clear": l_clear,
            "E": 30e6,
            "I": I_val,
        },
        "spans": [{"span_id": "S1", "length_m": l_clear}],
        "spans_m": [l_clear],
    }


def make_column(mid: str, cx: float, cy: float) -> dict:
    return {
        "member_id": mid,
        "member_type": "column",
        "type": "column",
        "start_point": None,
        "end_point": None,
        "center_point": {"x": cx, "y": cy},
        "boundary_polygon": None,
        "is_void": False,
        "meta": {"b": 300, "h": 300, "L_clear": 3.0},
        "spans": [],
        "spans_m": [],
    }


# ── Test 1: two collinear contiguous horizontal segments ─────────────────────

def test_two_collinear_contiguous_merge():
    b1 = make_beam("B1", 0, 0, 5000, 0)      # 5 m
    b2 = make_beam("B2", 5000, 0, 11000, 0)  # 6 m
    result = _group_collinear_beam_runs([b1, b2])

    beams = [m for m in result if m["member_type"] == "beam"]
    assert len(beams) == 1
    merged = beams[0]
    assert merged["spans_m"] == pytest.approx([5.0, 6.0], abs=0.001)
    assert merged["meta"]["L_clear"] == pytest.approx(11.0, abs=0.001)
    assert len(merged["spans"]) == 2
    assert merged["spans"][0]["span_id"] == "S1"
    assert merged["spans"][1]["span_id"] == "S2"
    assert merged["start_point"]["x"] == pytest.approx(0, abs=1)
    assert merged["end_point"]["x"] == pytest.approx(11000, abs=1)


# ── Test 2: three collinear segments merge into one three-span member ────────

def test_three_collinear_segments_merge():
    b1 = make_beam("B1", 0, 0, 6000, 0)
    b2 = make_beam("B2", 6000, 0, 12000, 0)
    b3 = make_beam("B3", 12000, 0, 18000, 0)
    result = _group_collinear_beam_runs([b1, b2, b3])

    beams = [m for m in result if m["member_type"] == "beam"]
    assert len(beams) == 1
    merged = beams[0]
    assert len(merged["spans_m"]) == 3
    assert sum(merged["spans_m"]) == pytest.approx(18.0, abs=0.01)
    assert len(merged["spans"]) == 3


# ── Test 3: reversed segment orientation still groups correctly ───────────────

def test_reversed_segment_orientation():
    b1 = make_beam("B1", 0, 0, 6000, 0)
    b2 = make_beam("B2", 12000, 0, 6000, 0)  # reversed: end→start
    result = _group_collinear_beam_runs([b1, b2])

    beams = [m for m in result if m["member_type"] == "beam"]
    assert len(beams) == 1
    assert len(beams[0]["spans_m"]) == 2
    assert sum(beams[0]["spans_m"]) == pytest.approx(12.0, abs=0.01)


# ── Test 4: parallel but offset beams (offset > 150 mm) remain separate ─────

def test_parallel_offset_beams_stay_separate():
    b1 = make_beam("B1", 0, 0, 6000, 0)        # y = 0
    b2 = make_beam("B2", 6000, 500, 12000, 500) # y = 500 mm (offset > _COLLINEAR_PERP_MM)
    result = _group_collinear_beam_runs([b1, b2])

    beams = [m for m in result if m["member_type"] == "beam"]
    assert len(beams) == 2


# ── Test 5: perpendicular beams sharing an endpoint remain separate ───────────

def test_perpendicular_beams_stay_separate():
    b1 = make_beam("B1", 0, 0, 6000, 0)      # horizontal
    b2 = make_beam("B2", 6000, 0, 6000, 6000) # vertical, shares endpoint (6000, 0)
    result = _group_collinear_beam_runs([b1, b2])

    beams = [m for m in result if m["member_type"] == "beam"]
    assert len(beams) == 2


# ── Test 6: single beam passes through unchanged ─────────────────────────────

def test_single_beam_unchanged():
    b1 = make_beam("B1", 0, 0, 5000, 0)
    result = _group_collinear_beam_runs([b1])

    beams = [m for m in result if m["member_type"] == "beam"]
    assert len(beams) == 1
    assert beams[0]["member_id"] == "B1"
    assert beams[0]["spans_m"] == pytest.approx([5.0], abs=0.001)


# ── Test 7: mix of groupable pair + perpendicular standalone ─────────────────

def test_mix_grouped_and_standalone():
    b1 = make_beam("B1", 0, 0, 6000, 0)
    b2 = make_beam("B2", 6000, 0, 12000, 0)   # collinear with B1
    b3 = make_beam("B3", 6000, 0, 6000, 8000)  # perpendicular
    result = _group_collinear_beam_runs([b1, b2, b3])

    beams = [m for m in result if m["member_type"] == "beam"]
    assert len(beams) == 2

    span_counts = sorted(len(b["spans_m"]) for b in beams)
    assert span_counts == [1, 2]


# ── Test 8: non-beam members pass through unchanged ──────────────────────────

def test_non_beam_members_pass_through():
    b1 = make_beam("B1", 0, 0, 5000, 0)
    col = make_column("C1", 5000, 0)
    result = _group_collinear_beam_runs([b1, col])

    columns = [m for m in result if m["member_type"] == "column"]
    assert len(columns) == 1
    assert columns[0]["member_id"] == "C1"


# ── Test 9: diagonal collinear segments merge correctly ──────────────────────

def test_diagonal_collinear_segments_merge():
    # 45-degree beams sharing endpoint at (5000, 5000)
    b1 = make_beam("B1", 0, 0, 5000, 5000)
    b2 = make_beam("B2", 5000, 5000, 10000, 10000)
    result = _group_collinear_beam_runs([b1, b2])

    beams = [m for m in result if m["member_type"] == "beam"]
    assert len(beams) == 1
    assert len(beams[0]["spans_m"]) == 2

"""
Combined-footing grouping (Workstream B, Slice 2c).

Where two base columns' estimated pad footings would overlap, the takedown now
merges them into a single combined footing (fed to the CombinedFootingSolver)
rather than emitting clashing pads.
"""
from core.loading.takedown import _group_combined_footings, _estimate_pad_B_m


def _foot(mid: str, x: float, y: float, n_sls: float):
    return {
        "member_id": f"F-{mid}",
        "member_type": "footing",
        "center_point": {"x": x, "y": y},
        "meta": {
            "footing_type": "pad",
            "N_uls": n_sls * 1.5,
            "N_sls": n_sls,
            "_source_column": mid,
            "qa": 150,
        },
    }


def _load(mid: str, n_sls: float):
    return {
        "member_id": f"F-{mid}",
        "member_type": "footing",
        "spans": [{"loads": {"n_uls": n_sls * 1.5, "n_sls": n_sls}}],
    }


def test_estimate_pad_size_matches_sls_rule():
    # A = N_sls * 1.1 / qa ; B = sqrt(A)
    assert _estimate_pad_B_m(900, 150) == _estimate_pad_B_m(900, 150)
    assert round(_estimate_pad_B_m(900, 150), 2) == 2.57
    assert _estimate_pad_B_m(900, 0) == 0.0


def test_close_columns_merge_into_combined_footing():
    # B ≈ 2.57 m each → pads overlap at 2 m spacing.
    members = [_foot("C1", 0, 0, 900), _foot("C2", 2000, 0, 900)]
    loads = [_load("C1", 900), _load("C2", 900)]
    m, ll = _group_combined_footings(members, loads, 150.0, "BS8110")

    assert len(m) == 1
    comb = m[0]
    assert comb["meta"]["footing_type"] == "combined"
    assert comb["meta"]["N_sls"] == 1800  # summed
    assert comb["meta"]["neighbour_N_uls"] == 900 * 1.5
    assert comb["meta"]["neighbour_dist_m"] == 2.0
    assert {fl["member_id"] for fl in ll} == {comb["member_id"]}


def test_distant_columns_stay_as_pads():
    members = [_foot("C1", 0, 0, 900), _foot("C2", 10000, 0, 900)]
    loads = [_load("C1", 900), _load("C2", 900)]
    m, _ = _group_combined_footings(members, loads, 150.0, "BS8110")
    assert len(m) == 2
    assert all(f["meta"]["footing_type"] == "pad" for f in m)


def test_each_column_pairs_at_most_once():
    # Three columns in a tight row: greedy pairs the nearest two, the third stays.
    members = [_foot("C1", 0, 0, 900), _foot("C2", 1500, 0, 900), _foot("C3", 9000, 0, 900)]
    loads = [_load("C1", 900), _load("C2", 900), _load("C3", 900)]
    m, _ = _group_combined_footings(members, loads, 150.0, "BS8110")
    types = sorted(f["meta"]["footing_type"] for f in m)
    assert types == ["combined", "pad"]


def test_single_footing_is_unchanged():
    members = [_foot("C1", 0, 0, 900)]
    loads = [_load("C1", 900)]
    m, ll = _group_combined_footings(members, loads, 150.0, "BS8110")
    assert m == members and ll == loads

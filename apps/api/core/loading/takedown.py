"""
core/loading/takedown.py
========================
Vertical Load Takedown Engine — Phase 5.

Performs top-down accumulation of beam reactions through column stacks using
BS 6399/EC1 live-load reduction factors.  After the horizontal (beam/slab)
analysis pass is complete, the analysis service calls
``VerticalLoadTakedownEngine.compute_column_axial_loads()`` to:

1. Build a beam→column connectivity map from support positions.
2. Trace each column stack from top storey to base.
3. Accumulate Gk and Qk floor-by-floor, applying reduction factors.
4. Auto-generate footing member dicts for ground-level (base) columns.

Returns
-------
(column_axial_loads, footing_members, footing_loads)
"""

from __future__ import annotations

import math
import logging
from typing import Any

from models.loading.schema import DesignCode
from core.loading.vertical_loaders import ColumnLoadAssembler

logger = logging.getLogger(__name__)

_SNAP_MM = 650.0  # max distance between a beam support point and a column centre


# ── Helper: split a ULS reaction back into Gk / Qk components ────────────────

def _split_reaction_gk_qk(
    R_uls: float,
    udl_gk: float,
    udl_qk: float,
    span_length_m: float,
) -> tuple[float, float]:
    """
    Return (R_gk, R_qk) at a support given ULS reaction R_uls.

    When characteristic UDL components are available we reuse their ratio
    to avoid back-calculating through partial-safety factors.  The reaction
    sharing ratio gk/(gk+qk) is applied to R_uls directly.

    If both UDLs are zero (edge case) assume dead-only.
    """
    total = udl_gk + udl_qk
    if total <= 0:
        return R_uls, 0.0
    ratio_gk = udl_gk / total
    return R_uls * ratio_gk, R_uls * (1.0 - ratio_gk)


# ── Support position reconstruction ──────────────────────────────────────────

def _get_beam_support_positions(beam: dict) -> list[dict]:
    """
    Return world-coordinate positions of all support points along a beam.

    For a single-span beam: [start, end].
    For a multi-span merged beam: start + one interior point per span
    boundary + end, interpolated along the beam axis.

    Positions are in mm (DXF coordinate space), matching column centre_point.
    """
    s = beam.get("start_point") or {}
    e = beam.get("end_point") or {}
    sx, sy = float(s.get("x", 0)), float(s.get("y", 0))
    ex, ey = float(e.get("x", 0)), float(e.get("y", 0))

    spans_m: list[float] = beam.get("spans_m") or []
    if len(spans_m) <= 1:
        return [
            {"x": sx, "y": sy, "idx": 0},
            {"x": ex, "y": ey, "idx": 1},
        ]

    total_mm = math.hypot(ex - sx, ey - sy)
    if total_mm < 1e-6:
        return [{"x": sx, "y": sy, "idx": i} for i in range(len(spans_m) + 1)]

    ux = (ex - sx) / total_mm
    uy = (ey - sy) / total_mm

    positions: list[dict] = []
    cum_mm = 0.0
    for i, L_m in enumerate(spans_m):
        positions.append({"x": sx + ux * cum_mm, "y": sy + uy * cum_mm, "idx": i})
        cum_mm += L_m * 1000.0
    positions.append({"x": ex, "y": ey, "idx": len(spans_m)})
    return positions


# ── Beam → column connectivity ────────────────────────────────────────────────

def _build_connectivity(
    members: list[dict],
    snap_mm: float = _SNAP_MM,
) -> dict[str, list[tuple[str, int]]]:
    """
    Map column_id → [(beam_id, support_index), ...].

    A support point is "at" a column if the 2-D distance between the support
    position and the column's centre_point is within *snap_mm*.

    Only columns and beams on the same storey are matched; when storey
    information is absent (single-storey model) all columns are candidates.
    """
    beams = [m for m in members if m.get("member_type") == "beam" or m.get("type") == "beam"]
    columns = [m for m in members if m.get("member_type") == "column" or m.get("type") == "column"]

    connectivity: dict[str, list[tuple[str, int]]] = {
        col["member_id"]: [] for col in columns
    }

    for beam in beams:
        b_storey = beam.get("storey")
        support_positions = _get_beam_support_positions(beam)

        for sp in support_positions:
            for col in columns:
                # Storey guard — skip if storeys are known and do not match
                c_storey = col.get("storey")
                if b_storey and c_storey and b_storey != c_storey:
                    continue

                cp = col.get("center_point") or {}
                cx = float(cp.get("x", 0))
                cy = float(cp.get("y", 0))
                dist = math.hypot(sp["x"] - cx, sp["y"] - cy)

                if dist <= snap_mm:
                    connectivity[col["member_id"]].append(
                        (beam["member_id"], sp["idx"])
                    )
                    break  # one column per support position

    return connectivity


# ── Column stack identification ───────────────────────────────────────────────

def _build_column_stacks(members: list[dict]) -> list[list[dict]]:
    """
    Return a list of column stacks, each ordered from top to bottom storey.

    Uses ``parent_column_id`` / ``child_column_id`` links created by
    ``storey_generator.link_column_stacks()``.  Falls back to treating each
    column as a singleton stack when linkage is absent.
    """
    col_by_id: dict[str, dict] = {
        m["member_id"]: m
        for m in members
        if m.get("member_type") == "column" or m.get("type") == "column"
    }

    if not col_by_id:
        return []

    # Find top-of-stack columns: those whose child_column_id is None/missing
    # (i.e., nothing sits on top of them) *or* whose child is not in this member set.
    def _child_id(col: dict) -> str | None:
        return col.get("meta", {}).get("child_column_id")

    def _parent_id(col: dict) -> str | None:
        return col.get("meta", {}).get("parent_column_id")

    tops = [
        col for col in col_by_id.values()
        if not _child_id(col) or _child_id(col) not in col_by_id
    ]

    if not tops:
        # Fallback: no linkage found — treat each column as its own stack
        return [[col] for col in col_by_id.values()]

    stacks: list[list[dict]] = []
    for top in tops:
        stack: list[dict] = [top]
        current = top
        visited: set[str] = {top["member_id"]}
        while True:
            pid = _parent_id(current)
            if not pid or pid not in col_by_id or pid in visited:
                break
            current = col_by_id[pid]
            stack.append(current)
            visited.add(pid)
        stacks.append(stack)

    return stacks


# ── Main takedown engine ──────────────────────────────────────────────────────

class VerticalLoadTakedownEngine:
    """
    Top-down vertical load accumulation and footing auto-generation.
    """

    @staticmethod
    def compute_column_axial_loads(
        members: list[dict],
        beam_analysis_results: dict[str, dict],
        beam_loading_data: dict[str, dict],
        project_params: dict[str, Any] | None = None,
        design_code: str = "BS8110",
    ) -> tuple[dict[str, dict], list[dict], list[dict]]:
        """
        Accumulate axial loads for every column and generate footing members.

        Parameters
        ----------
        members
            Flat list of all parsed members (from ``parsed_members.values()``).
        beam_analysis_results
            ``{beam_id: MemberAnalysisResult.model_dump()}`` for all horizontal
            members processed in Pass 1.
        beam_loading_data
            ``{beam_id: MemberLoadOutput.model_dump()}`` — provides Gk/Qk UDL
            values for the Gk/Qk reaction split.
        project_params
            Optional dict with project-level parameters (e.g. ``qa_kpa``).
        design_code
            "BS8110" or "EC2".

        Returns
        -------
        (column_axial_loads, footing_members, footing_loads)
            * ``column_axial_loads`` — ``{col_id: {N_uls, N_sls, gk_total,
              qk_total, storeys_supported, reduction_factor}}``
            * ``footing_members`` — list of auto-generated footing member dicts
              ready to inject into ``parsed_members``
            * ``footing_loads`` — minimal ``MemberLoadOutput``-shaped dicts for
              each footing, ready to inject into ``load_members``
        """
        params = project_params or {}
        qa_kpa = float(params.get("qa_kpa", 150.0))

        try:
            code_enum = DesignCode(design_code.upper())
        except ValueError:
            code_enum = DesignCode.BS8110

        members_by_id: dict[str, dict] = {m["member_id"]: m for m in members}
        connectivity = _build_connectivity(members, snap_mm=_SNAP_MM)
        stacks = _build_column_stacks(members)

        column_axial_loads: dict[str, dict] = {}

        for stack in stacks:
            accumulated_gk = 0.0
            accumulated_qk = 0.0

            for storey_index, col in enumerate(stack, start=1):
                col_id = col["member_id"]
                meta = col.get("meta", {})

                # ── Beam reactions framing into this column ──────────────
                for beam_id, support_idx in connectivity.get(col_id, []):
                    b_result = beam_analysis_results.get(beam_id, {})
                    reactions = b_result.get("reactions_kN", [])
                    if support_idx >= len(reactions):
                        continue
                    R_uls = float(reactions[support_idx])

                    # Retrieve characteristic UDLs for Gk/Qk split
                    b_load = beam_loading_data.get(beam_id, {})
                    udl_gk, udl_qk = _extract_udl_gk_qk(b_load, support_idx)
                    r_gk, r_qk = _split_reaction_gk_qk(R_uls, udl_gk, udl_qk, 0.0)

                    accumulated_gk += r_gk
                    accumulated_qk += r_qk

                # ── Column self-weight ───────────────────────────────────
                b_mm = float(meta.get("b_mm") or meta.get("b") or 300.0)
                h_mm = float(meta.get("h_mm") or meta.get("h") or 300.0)
                l_clear = float(meta.get("L_clear") or meta.get("l_clear") or 3.0)
                sw_gk = ColumnLoadAssembler.calculate_self_weight(b_mm, h_mm, l_clear)
                accumulated_gk += sw_gk

                # ── Accumulate and factor ────────────────────────────────
                col_loads = ColumnLoadAssembler.accumulate_column_loads(
                    incoming_gk=accumulated_gk,
                    incoming_qk=accumulated_qk,
                    num_floors_supported=storey_index,
                    self_weight_gk=0.0,  # already included above
                    code=code_enum,
                )

                column_axial_loads[col_id] = {
                    "N_uls": col_loads["uls_axial_load"],
                    "N_sls": col_loads["total_gk"] + col_loads["reduced_qk"],
                    "gk_total": col_loads["total_gk"],
                    "qk_total": col_loads["reduced_qk"],
                    "storeys_supported": storey_index,
                    "reduction_factor": col_loads["reduction_factor"],
                }
                logger.debug(
                    "Takedown %s (storey %d): N_uls=%.1f kN",
                    col_id, storey_index, col_loads["uls_axial_load"]
                )

                # Carry forward for next storey down
                accumulated_gk = col_loads["total_gk"]
                accumulated_qk = col_loads["reduced_qk"]

        # ── Auto-generate footing members at base columns ────────────────
        footing_members: list[dict] = []
        footing_loads: list[dict] = []

        for col_id, axial in column_axial_loads.items():
            col = members_by_id.get(col_id, {})
            # Ground-level columns: no parent_column_id (nothing below them)
            if col.get("meta", {}).get("parent_column_id"):
                continue

            col_meta = col.get("meta", {})
            fid = f"F-{col_id}"
            N_sls = axial["gk_total"] + axial["qk_total"]
            N_uls = axial["N_uls"]
            c1 = float(col_meta.get("b_mm") or col_meta.get("b") or 300.0)
            c2 = float(col_meta.get("h_mm") or col_meta.get("h") or 300.0)

            footing_members.append({
                "member_id": fid,
                "member_type": "footing",
                "type": "footing",
                "center_point": col.get("center_point"),
                "start_point": None,
                "end_point": None,
                "boundary_polygon": None,
                "is_void": False,
                "spans": [],
                "spans_m": [],
                "meta": {
                    "footing_type": "pad",
                    "c1": c1,
                    "c2": c2,
                    "qa": qa_kpa,
                    "N_uls": N_uls,
                    "N_sls": N_sls,
                    "M_uls": 0.0,
                    "_source_column": col_id,
                },
            })

            footing_loads.append({
                "member_id": fid,
                "member_type": "footing",
                "design_code": design_code,
                "spans": [{
                    "span_id": "S1",
                    "length_m": 1.0,
                    "loads": {"n_uls": N_uls, "n_sls": N_sls},
                }],
                "combination_used": "1.4Gk+1.6Qk",
                "notes": f"Auto-generated from column {col_id} base reaction",
            })

            logger.info("Auto-generated footing %s: N_uls=%.1f kN, N_sls=%.1f kN", fid, N_uls, N_sls)

        # ── Group adjacent base columns into combined footings ────────────
        # Where two columns' estimated (SLS) pad footings would overlap, designing
        # them as separate pads is wrong — merge them into a single combined
        # footing fed to the CombinedFootingSolver. Greedy nearest-pair: each
        # column pairs at most once. center_point coordinates are in millimetres.
        footing_members, footing_loads = _group_combined_footings(
            footing_members, footing_loads, qa_kpa, design_code
        )

        return column_axial_loads, footing_members, footing_loads


# ── Combined-footing grouping ─────────────────────────────────────────────────

def _estimate_pad_B_m(N_sls_kN: float, qa_kpa: float) -> float:
    """SLS-sized square pad side (m), matching PadFootingSolver's sizing rule."""
    if qa_kpa <= 0:
        return 0.0
    area = (N_sls_kN * 1.1) / qa_kpa  # +10% self-weight allowance
    return math.sqrt(area) if area > 0 else 0.0


def _group_combined_footings(
    footing_members: list[dict],
    footing_loads: list[dict],
    qa_kpa: float,
    design_code: str,
) -> tuple[list[dict], list[dict]]:
    """
    Merge pairs of base-column footings whose estimated pads would overlap into
    single combined footings.

    Greedy nearest-pair: iterate footings, pair each unpaired one with its nearest
    unpaired neighbour when their pads overlap (centre spacing < ½B_i + ½B_j). The
    combined footing carries both column loads and the inputs the
    ``CombinedFootingSolver`` needs (``neighbour_N_uls``, ``neighbour_dist_m``,
    ``edge_distance_m``). Unpaired footings stay as pads.
    """
    n = len(footing_members)
    if n < 2:
        return footing_members, footing_loads

    paired: set[int] = set()
    combined_members: list[dict] = []
    combined_loads: list[dict] = []

    def _centre(fm: dict) -> tuple[float, float] | None:
        cp = fm.get("center_point") or {}
        if "x" not in cp or "y" not in cp:
            return None
        return float(cp["x"]), float(cp["y"])

    for i in range(n):
        if i in paired:
            continue
        ci = _centre(footing_members[i])
        if ci is None:
            continue
        B_i = _estimate_pad_B_m(footing_members[i]["meta"]["N_sls"], qa_kpa)

        best_j: int | None = None
        best_d_mm: float | None = None
        for j in range(n):
            if j == i or j in paired:
                continue
            cj = _centre(footing_members[j])
            if cj is None:
                continue
            d_mm = math.hypot(ci[0] - cj[0], ci[1] - cj[1])
            if best_d_mm is None or d_mm < best_d_mm:
                best_d_mm, best_j = d_mm, j

        if best_j is None or best_d_mm is None:
            continue

        fj = footing_members[best_j]
        B_j = _estimate_pad_B_m(fj["meta"]["N_sls"], qa_kpa)
        d_m = best_d_mm / 1000.0
        if d_m <= 0 or d_m >= (B_i / 2.0 + B_j / 2.0):
            continue  # pads clear — keep both as pads

        # Merge i and best_j into one combined footing.
        paired.add(i)
        paired.add(best_j)
        fi = footing_members[i]
        cj = _centre(fj)
        assert cj is not None
        mid = {"x": (ci[0] + cj[0]) / 2.0, "y": (ci[1] + cj[1]) / 2.0}
        src_i = fi["meta"].get("_source_column", fi["member_id"])
        src_j = fj["meta"].get("_source_column", fj["member_id"])
        cid = f"FC-{src_i}-{src_j}"
        N_uls_total = fi["meta"]["N_uls"] + fj["meta"]["N_uls"]
        N_sls_total = fi["meta"]["N_sls"] + fj["meta"]["N_sls"]

        combined_members.append({
            "member_id": cid,
            "member_type": "footing",
            "type": "footing",
            "center_point": mid,
            "start_point": None,
            "end_point": None,
            "boundary_polygon": None,
            "is_void": False,
            "spans": [],
            "spans_m": [],
            "meta": {
                "footing_type": "combined",
                "qa": qa_kpa,
                "N_uls": fi["meta"]["N_uls"],
                "N_sls": N_sls_total,
                "neighbour_N_uls": fj["meta"]["N_uls"],
                "neighbour_dist_m": round(d_m, 3),
                "edge_distance_m": round(min(d_m * 0.5, 0.5), 3),
                "M_uls": 0.0,
                "_source_columns": [src_i, src_j],
            },
        })
        combined_loads.append({
            "member_id": cid,
            "member_type": "footing",
            "design_code": design_code,
            "spans": [{
                "span_id": "S1",
                "length_m": round(d_m, 3) or 1.0,
                "loads": {"n_uls": N_uls_total, "n_sls": N_sls_total},
            }],
            "combination_used": "1.4Gk+1.6Qk",
            "notes": f"Combined footing for columns {src_i} & {src_j}",
        })
        logger.info("Grouped %s + %s into combined footing %s (spacing %.2f m)", src_i, src_j, cid, d_m)

    if not paired:
        return footing_members, footing_loads

    kept_members = [fm for k, fm in enumerate(footing_members) if k not in paired] + combined_members
    kept_ids = {fm["member_id"] for fm in kept_members}
    kept_loads = [fl for fl in footing_loads if fl["member_id"] in kept_ids] + combined_loads
    return kept_members, kept_loads


# ── UDL Gk/Qk extraction helper ──────────────────────────────────────────────

def _extract_udl_gk_qk(
    b_load: dict,
    support_idx: int,
) -> tuple[float, float]:
    """
    Extract characteristic UDL components (gk, qk) from a MemberLoadOutput dict.

    Tries per-span loads first (``spans[i].loads.udl_gk``), then falls back
    to the first span's values, then to zeroes.
    """
    spans: list[dict] = b_load.get("spans", [])
    # Span index: support_idx 0 → span 0, support_idx N → span N-1 (end support)
    span_idx = min(max(support_idx - 1, 0), len(spans) - 1) if spans else -1

    def _from_span(s: dict) -> tuple[float, float]:
        loads: dict = s.get("loads", {})
        gk = float(loads.get("udl_gk", 0) or loads.get("dead_udl_kN_per_m", 0) or 0)
        qk = float(loads.get("udl_qk", 0) or loads.get("live_udl_kN_per_m", 0) or 0)
        return gk, qk

    if 0 <= span_idx < len(spans):
        return _from_span(spans[span_idx])
    if spans:
        return _from_span(spans[0])
    return 0.0, 0.0

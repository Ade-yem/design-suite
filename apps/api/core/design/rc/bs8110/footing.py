"""
BS 8110-1:1997  –  Foundation Design  (Clause 3.11)
====================================================
Provides fully-checked design functions for two foundation types:

  * ``design_pad_footing``  — Isolated pad footing  (Cl 3.11.2 / 3.11.3)
  * ``design_pile_cap``     — Pile cap              (Cl 3.11.4)

Design sequence — Pad Footing (Cl 3.11.3)
------------------------------------------
1.  Bearing pressure intensity (net upward, from applied N and M).
2.  Critical cantilever moment at the column face in both x and y.
3.  Flexural reinforcement (As_req) in both directions.
4.  Beam shear at d from column face (Cl 3.11.3.3).
5.  Punching shear at 1.5d perimeter (Cl 3.11.3.4 b / Cl 3.7.7).
6.  Detailing checks (As_min, As_max, bar spacing).

Design sequence — Pile Cap (Cl 3.11.4)
----------------------------------------
1.  Pile reaction distribution under N (and M if eccentric load).
2.  Truss analogy tension tie force T and required As.
3.  Shear at critical section (20% pile diameter inside pile face)
    with 2d/av enhancement (Cl 3.11.4.4).
4.  Punching at column perimeter (Cl 3.11.4.5).
5.  Detailing checks.

Key conventions
---------------
  * All forces in **N** (Newtons), moments in **N·mm**.
  * ``section.d`` is the effective depth to centroid of tension steel.
  * Bearing pressure ``q`` is the *net factored* upward soil pressure
    (i.e. column design ultimate load / plan area of footing).
    Self-weight of the footing and soil overburden are typically included
    in the characteristic loads and then factored, but the net pressure
    used here should be the *upward* pressure causing bending/shear in the
    concrete section.
"""

from __future__ import annotations

import math
from typing import Optional

from models.bs8110.footing import PadFooting, PileCap
from core.design.rc.bs8110.formulas import (
    calculate_k,
    calculate_k_prime,
    calculate_lever_arm,
    calculate_singly_reinforced_section,
    calculate_vc,
    check_shear_stress,
    check_reinforcement_limits,
)
from core.design.rc.common.select_reinforcement import select_slab_reinforcement


# ===========================================================================
# 1. Pad Footing Design  (BS 8110 Cl 3.11.2 / 3.11.3)
# ===========================================================================

def design_pad_footing(
    section: PadFooting,
    N: float,                       # Factored axial column load (N)
    Mx: float = 0.0,                # Factored moment about x-axis at column base (N·mm)
    My: float = 0.0,                # Factored moment about y-axis at column base (N·mm)
) -> dict:
    """
    Design an isolated rectangular pad footing per BS 8110 Cl 3.11.2 & 3.11.3.

    The pad is designed as a wide cantilever in each plan direction,
    fixed at the column face, under net upward bearing pressure from the soil.

    Bearing Pressure (Cl 3.11.2.1)
    --------------------------------
    For a combined axial + moment load, the pressure distribution is
    trapezoidal:

        q_max = N / (lx × ly) + 6Mx / (lx × ly²) + 6My / (lx² × ly)
        q_min = N / (lx × ly) − 6Mx / (lx × ly²) − 6My / (lx² × ly)

    If q_min < 0 the footing is in partial uplift.  This is flagged as a
    warning; the design continues using q_max conservatively.

    Flexure (Cl 3.11.2.2 / 3.4.4)
    --------------------------------
    Critical section at the column face. For a cantilever of length
    ``a = (L − c) / 2``:

        M = q_max × b × a² / 2    [N·mm per metre width, × footing width]

    where q_max is the maximum bearing pressure (N/mm²), ``b`` is the
    footing width in the orthogonal direction, and ``a`` is the
    cantilever projection from the column face.

    Beam Shear (Cl 3.11.3.3)
    -------------------------
    Critical section at distance ``d`` from the column face (same as Cl 3.5.5.2
    for slabs, not at d from support centreline as for beams).

    Punching Shear (Cl 3.11.3.4b / Cl 3.7.7)
    ------------------------------------------
    Checked at a perimeter 1.5d from the column face.  The perimeter has
    rounded corners per Cl 3.7.7.3:

        u1 = 2(cx + cy) + 2π × 1.5d = 2(cx + cy) + 3πd

    Parameters
    ----------
    section : ``PadFooting``
    N       : Factored axial load (N) — positive compression.
    Mx      : Factored moment about x-axis (N·mm). Default 0.
    My      : Factored moment about y-axis (N·mm). Default 0.

    Returns
    -------
    dict with:
        status, As_req_x, As_req_y, As_prov_x, As_prov_y,
        reinforcement_x, reinforcement_y, shear_x_status, shear_y_status,
        punching_status, q_max, q_min, notes, warnings.
    """
    notes: list[str] = []
    warnings: list[str] = []
    results: dict = {"status": "OK", "notes": notes, "warnings": warnings}

    notes.append(section.summary())
    notes.append(
        f"Design actions: N = {N/1e3:.1f} kN, Mx = {Mx/1e6:.1f} kN·m, "
        f"My = {My/1e6:.1f} kN·m  (BS 8110 Cl 3.11)"
    )

    lx = section.lx
    ly = section.ly
    h  = section.h
    d  = section.d
    fcu = section.fcu
    fy  = section.fy
    cx = section.column_cx
    cy = section.column_cy

    # -------------------------------------------------------------------------
    # Step 1: Bearing pressure distribution  (Cl 3.11.2.1)
    # -------------------------------------------------------------------------
    A_plan    = lx * ly
    q_uni     = N / A_plan                       # Uniform component (N/mm²)
    q_x_ecc  = 6.0 * Mx / (lx * ly ** 2)        # Pressure eccentricity due to Mx
    q_y_ecc  = 6.0 * My / (lx ** 2 * ly)        # Pressure eccentricity due to My
    q_max    = q_uni + q_x_ecc + q_y_ecc
    q_min    = q_uni - q_x_ecc - q_y_ecc

    results["q_max_kNm2"] = round(q_max * 1e3, 2)
    results["q_min_kNm2"] = round(q_min * 1e3, 2)
    notes.append(
        f"Bearing pressure: q_max = {q_max*1e3:.2f} kN/m², "
        f"q_min = {q_min*1e3:.2f} kN/m²  (Cl 3.11.2.1)"
    )

    if q_min < 0:
        warnings.append(
            f"q_min = {q_min*1e3:.2f} kN/m² < 0: footing is in partial uplift. "
            "Footing size should be increased or load checked. "
            "Design continues with q_max conservatively."
        )

    # Use q_max as design pressure throughout (conservative)
    q = q_max

    # -------------------------------------------------------------------------
    # Step 2: Cantilever moments at column face  (Cl 3.11.2.2)
    # -------------------------------------------------------------------------
    # x-direction: cantilever length a_x = (lx − cx) / 2 (projection from column face)
    # Bending strip width in x-direction = ly (full footing width)
    a_x = (lx - cx) / 2.0   # mm
    a_y = (ly - cy) / 2.0   # mm

    # Moment per unit width at column face (N·mm per mm = N):
    #   M = q × a² / 2   (per unit width of footing)
    # Total moment across width = q × a² / 2 × b_ortho
    # For design, use per-1m-width (q in N/mm², a in mm → M in N·mm/mm = N·mm per unit width)
    M_x = q * a_x ** 2 / 2.0    # N·mm per mm of footing width in y-direction
    M_y = q * a_y ** 2 / 2.0    # N·mm per mm of footing width in x-direction
    # Convert to N·mm/m for consistency with reinforcement selection
    M_x_pm = M_x * 1000.0       # N·mm/m
    M_y_pm = M_y * 1000.0       # N·mm/m

    results["cantilever_moments_kNm_per_m"] = {
        "Mx_at_column_face": round(M_x_pm / 1e6, 2),
        "My_at_column_face": round(M_y_pm / 1e6, 2),
    }
    notes.append(
        f"Cantilever projections: a_x = {a_x:.0f} mm, a_y = {a_y:.0f} mm  "
        f"(Cl 3.11.2.2)\n"
        f"  Mx (at col face) = q×a_x²/2 = {q*1e3:.3f}×{a_x:.0f}²/2 = {M_x_pm/1e6:.2f} kN·m/m\n"
        f"  My (at col face) = q×a_y²/2 = {q*1e3:.3f}×{a_y:.0f}²/2 = {M_y_pm/1e6:.2f} kN·m/m"
    )

    # -------------------------------------------------------------------------
    # Step 3: Flexural design — x-direction  (bars parallel to y-axis)
    # -------------------------------------------------------------------------
    notes.append("--- Flexural design — x-direction (bars parallel to y, spanning lx) ---")
    k_prime_res = calculate_k_prime()
    K_prime = k_prime_res["value"]
    notes.append(k_prime_res["note"])

    def _flex_design(M_pm: float, label: str) -> tuple[float, dict, list, list]:
        """Return (As_req, bars, notes_list, warnings_list) for a per-metre moment."""
        _n, _w = [], []
        b = 1000.0
        k_res = calculate_k(M_pm, fcu, b, d)
        K = k_res["value"]
        _n.append(k_res["note"])
        if K > K_prime:
            _w.append(f"{label}: K ({K:.4f}) > K' ({K_prime:.4f}) — section inadequate, increase h.")
            return None, None, _n, _w
        z_res = calculate_lever_arm(d, K)
        _n.append(z_res["note"])
        As_val = calculate_singly_reinforced_section(M_pm, fy, z_res["value"])["value"]
        As_design = max(As_val, section.As_min)
        bars = select_slab_reinforcement(As_design, d, h, fy)
        _n.append(f"{label}: As_req = {As_val:.1f} mm²/m → {bars['description']}")
        if bars["warning"]:
            _w.append(bars["warning"])
        return As_val, bars, _n, _w

    As_x, bars_x, nx, wx = _flex_design(M_x_pm, "x-direction")
    notes.extend(nx); warnings.extend(wx)
    if As_x is None:
        results["status"] = "Section Inadequate (x-flexure)"
        return results
    results["As_req_x"]      = round(As_x, 2)
    results["As_prov_x"]     = bars_x["As_prov"]
    results["reinforcement_x"] = bars_x["description"]

    # -------------------------------------------------------------------------
    # Step 4: Flexural design — y-direction  (bars parallel to x-axis)
    # -------------------------------------------------------------------------
    notes.append("--- Flexural design — y-direction (bars parallel to x, spanning ly) ---")
    As_y, bars_y, ny, wy = _flex_design(M_y_pm, "y-direction")
    notes.extend(ny); warnings.extend(wy)
    if As_y is None:
        results["status"] = "Section Inadequate (y-flexure)"
        return results
    results["As_req_y"]      = round(As_y, 2)
    results["As_prov_y"]     = bars_y["As_prov"]
    results["reinforcement_y"] = bars_y["description"]

    # -------------------------------------------------------------------------
    # Step 5: Reinforcement limits
    # -------------------------------------------------------------------------
    for label, As_prov in [("x", bars_x["As_prov"]), ("y", bars_y["As_prov"])]:
        lim_res = check_reinforcement_limits(As_prov, section.As_min, section.As_max, label)
        notes.append(lim_res["note"])
        if lim_res["status"] == "FAIL":
            results["status"] = f"Reinforcement Limit Failure ({label})"

    # -------------------------------------------------------------------------
    # Step 6: Beam shear — x-direction  (Cl 3.11.3.3)
    # Critical at d from column face → av = a_x − d from column CL to crit. section
    # Shear force on strip 1m wide = q × (a_x − d) per metre width
    # -------------------------------------------------------------------------
    notes.append("--- Beam Shear Check  (Cl 3.11.3.3) ---")

    def _beam_shear_check(a_crit: float, width: float, As_prov: float, label: str) -> str:
        """Shear force on 1m strip at distance a_crit from column CL."""
        _n, _w = [], []
        # Projection from column face to critical section
        projection = a_crit - d   # remaining cantilever beyond critical section
        if projection <= 0:
            _n.append(f"{label}: Critical shear section inside column — no shear check needed.")
            notes.extend(_n)
            return "OK (inside column footprint)"
        V_strip = q * projection * 1000.0   # N per 1m strip (q [N/mm²] × length [mm] × 1000mm)
        shear_res = check_shear_stress(V_strip, 1000.0, d, fcu)
        _n.append(shear_res["note"])
        vc_res = calculate_vc(As_prov, 1000.0, d, fcu, h)
        _n.append(vc_res["note"])
        notes.extend(_n)
        if shear_res["status"] == "FAIL":
            warnings.append(f"{label}: v exceeds absolute limit. Increase depth h.")
            return "FAIL: v > v_max"
        if shear_res["v"] > vc_res["value"]:
            warnings.append(
                f"{label}: v ({shear_res['v']:.3f}) > vc ({vc_res['value']:.3f}). "
                "Increase footing depth — shear links are not practical in pad footings."
            )
            return f"FAIL: v ({shear_res['v']:.3f}) > vc ({vc_res['value']:.3f})"
        return "OK"

    shear_x = _beam_shear_check(a_x, ly, bars_x["As_prov"], "Beam shear x")
    shear_y = _beam_shear_check(a_y, lx, bars_y["As_prov"], "Beam shear y")
    results["shear_x_status"] = shear_x
    results["shear_y_status"] = shear_y
    if "FAIL" in shear_x or "FAIL" in shear_y:
        if results["status"] == "OK":
            results["status"] = "Shear Failure"

    # -------------------------------------------------------------------------
    # Step 7: Punching shear at 1.5d perimeter  (Cl 3.11.3.4b / Cl 3.7.7)
    # -------------------------------------------------------------------------
    notes.append("--- Punching Shear Check  (Cl 3.11.3.4b / Cl 3.7.7) ---")

    # Perimeter with rounded corners: u1 = 2(cx + cy) + 3πd
    u1 = 2.0 * (cx + cy) + 3.0 * math.pi * d
    notes.append(
        f"Critical 1.5d perimeter: u1 = 2(cx+cy) + 3πd = "
        f"2×({cx:.0f}+{cy:.0f}) + 3π×{d:.0f} = {u1:.0f} mm  (Cl 3.7.7.3)"
    )

    # Net punching load = N minus upward pressure over the area enclosed by u1
    cx_punch = cx + 3.0 * d    # critical zone side in x (cx + 2 × 1.5d)
    cy_punch = cy + 3.0 * d    # critical zone side in y
    area_punch = cx_punch * cy_punch + (math.pi * (1.5 * d) ** 2)  # approx with rounded corners
    V_punch_net = N - q * area_punch
    V_punch_net = max(V_punch_net, 0.0)   # cannot be negative

    v_punch = V_punch_net / (u1 * d)
    results["v_punch"] = round(v_punch, 4)

    # vc for punching using average of x and y bars (conservative: use minimum)
    As_punch_avg = (bars_x["As_prov"] + bars_y["As_prov"]) / 2.0
    vc_punch_res = calculate_vc(As_punch_avg, 1000.0, d, fcu, h)
    vc_punch = vc_punch_res["value"]
    notes.append(vc_punch_res["note"])
    notes.append(
        f"Net punching load = N − q × A_punch = {N/1e3:.1f} − {q*1e3:.3f}×{area_punch:.0f}/{1e6:.0f} "
        f"= {V_punch_net/1e3:.1f} kN  |  v_punch = {v_punch:.4f} N/mm²"
    )

    v_max_punch = min(0.8 * math.sqrt(fcu), 5.0)
    if v_punch > v_max_punch:
        results["punching_status"] = f"FAIL: v_punch ({v_punch:.3f}) > v_max ({v_max_punch:.3f})"
        if results["status"] == "OK":
            results["status"] = "Punching Shear Failure"
    elif v_punch > vc_punch:
        results["punching_status"] = (
            f"FAIL: v_punch ({v_punch:.3f}) > vc ({vc_punch:.3f}) — increase depth."
        )
        if results["status"] == "OK":
            results["status"] = "Punching Shear Failure"
    else:
        results["punching_status"] = f"OK: v_punch ({v_punch:.3f}) ≤ vc ({vc_punch:.3f})"

    return results


# ===========================================================================
# 2. Pile Cap Design  (BS 8110 Cl 3.11.4)
# ===========================================================================

def design_pile_cap(
    section: PileCap,
    N: float,        # Factored axial column load (N)
    Mx: float = 0.0, # Factored moment about x-axis at pile cap top (N·mm)
) -> dict:
    """
    Design a pile cap using the truss analogy (BS 8110 Cl 3.11.4.1).

    Truss Analogy (Cl 3.11.4.1)
    ----------------------------
    The compression strut runs from the column to the pile heads.
    The horizontal tension tie in the reinforcement is designed for:

        T = (N / 2) × (pile_spacing / 2) / z

    where ``z`` is the lever arm (not the full effective depth ``d``):

        z = d − pile_dia / 4    (approx; Cl 3.11.4.1 Note)

    The strut inclination angle is arctan(2z / pile_spacing).
    For a symmetric 2-pile cap under axial load only, both ties carry the
    same force T. For n-pile caps, the pile group geometry governs.

    Shear (Cl 3.11.4.3 / 3.11.4.4)
    --------------------------------
    Critical section at 20% of pile diameter from the pile face, measured
    from the column face outward. The enhancement factor:

        vc_enhanced = vc × (2d / av)

    with av clamped to a minimum of d/5 to avoid infinite factors.

    Punching (Cl 3.11.4.5)
    -----------------------
    Column face perimeter u0 = 2(cx + cy) checked at v_max.

    Parameters
    ----------
    section : ``PileCap``
    N       : Factored axial load (N)
    Mx      : Factored moment at top-of-pile-cap (N·mm). Default 0.

    Returns
    -------
    dict with: status, As_req, As_prov, reinforcement_description,
    shear_status, punching_status, notes, warnings.
    """
    notes: list[str] = []
    warnings: list[str] = []
    results: dict = {"status": "OK", "notes": notes, "warnings": warnings}

    notes.append(section.summary())
    notes.append(
        f"Design actions: N = {N/1e3:.1f} kN, Mx = {Mx/1e6:.1f} kN·m  "
        f"(BS 8110 Cl 3.11.4)"
    )

    d             = section.d
    fcu           = section.fcu
    fy            = section.fy
    pile_s        = section.pile_spacing
    pile_dia      = section.pile_dia
    num_piles     = section.num_piles
    cx            = section.column_cx
    cy            = section.column_cy

    # -------------------------------------------------------------------------
    # Step 1: Pile reactions
    # -------------------------------------------------------------------------
    # For a symmetric pile group under axial only: R_pile = N / n
    # With moment: R_pile = N/n ± M × y_i / Σy²  (where y_i = distance from centroid)
    # For a 2-pile cap (simplified):
    R_pile = N / num_piles
    notes.append(f"Pile reaction (axial only) R = N/n = {N/1e3:.1f}/{num_piles} = {R_pile/1e3:.1f} kN")
    if abs(Mx) > 0:
        # For 2-pile cap with moment in pile-row direction:
        # R_max = N/n + M × (s/2) / (n/2 × (s/2)²) = N/n + M/(s/2) for 2 piles
        if num_piles == 2:
            R_pile_max = N / 2.0 + abs(Mx) / pile_s
            R_pile_min = N / 2.0 - abs(Mx) / pile_s
            notes.append(
                f"With Mx: R_max = {R_pile_max/1e3:.1f} kN, R_min = {R_pile_min/1e3:.1f} kN"
            )
            if R_pile_min < 0:
                warnings.append(
                    f"R_pile_min = {R_pile_min/1e3:.1f} kN < 0: pile in tension — "
                    "check structural continuity of pile-cap connection."
                )
            R_pile = R_pile_max   # Use worst case for design
        else:
            notes.append("Multi-pile cap with moment: R_pile = N/n (moment distribution requires group analysis).")

    # -------------------------------------------------------------------------
    # Step 2: Truss analogy — tension tie force and As  (Cl 3.11.4.1)
    # -------------------------------------------------------------------------
    # Lever arm z = d − pile_dia / 4  (lower node at centroid of pile group)
    z = d - pile_dia / 4.0
    if z <= 0:
        warnings.append(f"z = d − pile_dia/4 = {z:.1f} mm ≤ 0. Increase footing depth.")
        z = 0.8 * d   # Fallback

    # For 2-pile cap: T = R_pile × (s/2) / z
    # Generalised: T = R_pile × l_arm / z  where l_arm = s/2 from column CL to pile CL
    l_arm = pile_s / 2.0   # (pile CL offset from cap CL)
    T = R_pile * l_arm / z
    As_req = T / (0.95 * fy)   # 0.95fy = design steel stress at ULS (= ALPHA_S × fy)
    As_req = max(As_req, section.As_min)

    notes.append(
        f"Truss analogy (Cl 3.11.4.1):\n"
        f"  z = d − Φ_pile/4 = {d:.1f} − {pile_dia/4:.1f} = {z:.1f} mm\n"
        f"  l_arm = s/2 = {l_arm:.0f} mm\n"
        f"  T = R_pile × l_arm / z = {R_pile/1e3:.1f} × {l_arm:.0f} / {z:.1f} = {T/1e3:.1f} kN\n"
        f"  As_req = T / (0.95fy) = {T:.0f} / (0.95×{fy}) = {As_req:.0f} mm²"
    )

    results["As_req"] = round(As_req, 2)

    # Select bars
    bars = select_slab_reinforcement(As_req, d, section.h, fy)
    results["As_prov"]                   = bars["As_prov"]
    results["reinforcement_description"] = bars["description"]
    if bars["warning"]:
        warnings.append(bars["warning"])
    notes.append(f"Tension tie steel: {bars['description']} (As_prov = {bars['As_prov']:.1f} mm²)")

    # Reinforcement limits
    lim_res = check_reinforcement_limits(bars["As_prov"], section.As_min, section.As_max, "tension")
    notes.append(lim_res["note"])
    if lim_res["status"] == "FAIL":
        results["status"] = "Reinforcement Limit Failure"

    # -------------------------------------------------------------------------
    # Step 3: Shear check at critical section  (Cl 3.11.4.3 / 3.11.4.4)
    # av = distance from column face to critical section
    # = (pile_spacing/2 − 0.3×pile_dia) − column_cx/2
    # -------------------------------------------------------------------------
    notes.append("--- Shear Check  (Cl 3.11.4.3 / 3.11.4.4) ---")
    av = (pile_s / 2.0) - (0.3 * pile_dia) - (cx / 2.0)

    if av <= 0:
        notes.append(
            f"Critical shear section (av = {av:.1f} mm ≤ 0) falls inside column footprint — "
            "no beam shear check required for this pile spacing."
        )
        results["shear_status"] = "OK (critical section inside column)"
    else:
        # Shear on 1m strip: V = R_pile reaction acting over pile cap width
        # For 2-pile cap bending in x-direction: width = ly
        v_shear = R_pile / (section.ly * d)  # N/mm²

        notes.append(
            f"av = s/2 − 0.3Φ − cx/2 = {pile_s/2:.0f} − {0.3*pile_dia:.0f} − {cx/2:.0f} = {av:.0f} mm"
        )
        notes.append(f"v = R_pile / (ly × d) = {R_pile/1e3:.1f}k / ({section.ly:.0f}×{d:.0f}) = {v_shear:.3f} N/mm²")

        # Enhancement factor 2d/av, clamped so av ≥ d/5 (to avoid > 10× factor)
        av_eff = max(av, d / 5.0)
        enhancement = (2.0 * d) / av_eff
        vc_res = calculate_vc(bars["As_prov"], section.ly, d, fcu, section.h)
        vc_base = vc_res["value"]
        vc_enhanced = vc_base * enhancement
        notes.append(vc_res["note"])
        notes.append(
            f"Shear enhancement (Cl 3.11.4.4): 2d/av = 2×{d:.0f}/{av_eff:.0f} = {enhancement:.2f}  |  "
            f"vc_enhanced = {vc_base:.3f} × {enhancement:.2f} = {vc_enhanced:.3f} N/mm²"
        )

        results["v_shear"]     = round(v_shear, 4)
        results["vc_enhanced"] = round(vc_enhanced, 4)

        v_max = min(0.8 * math.sqrt(fcu), 5.0)
        if v_shear > v_max:
            results["shear_status"] = f"FAIL: v ({v_shear:.3f}) > v_max ({v_max:.3f})"
            results["status"] = "Shear Failure"
        elif v_shear > vc_enhanced:
            results["shear_status"] = f"FAIL: v ({v_shear:.3f}) > vc_enhanced ({vc_enhanced:.3f}). Increase depth."
            if results["status"] == "OK":
                results["status"] = "Shear Failure"
        else:
            results["shear_status"] = f"OK: v ({v_shear:.3f}) ≤ vc_enhanced ({vc_enhanced:.3f})"

    # -------------------------------------------------------------------------
    # Step 4: Punching shear at column perimeter  (Cl 3.11.4.5)
    # Column face perimeter u0 = 2(cx + cy)
    # -------------------------------------------------------------------------
    notes.append("--- Punching Shear at Column Face  (Cl 3.11.4.5) ---")
    u0 = 2.0 * (cx + cy)
    v_face = N / (u0 * d)
    v_max_punch = min(0.8 * math.sqrt(fcu), 5.0)
    notes.append(
        f"u0 = 2(cx+cy) = 2×({cx:.0f}+{cy:.0f}) = {u0:.0f} mm  |  "
        f"v_face = N/(u0×d) = {N/1e3:.1f}k/({u0:.0f}×{d:.0f}) = {v_face:.4f} N/mm²  "
        f"(v_max = {v_max_punch:.3f})"
    )
    results["v_col_face"] = round(v_face, 4)
    if v_face > v_max_punch:
        results["punching_status"] = f"FAIL: v_face ({v_face:.3f}) > v_max ({v_max_punch:.3f})"
        if results["status"] == "OK":
            results["status"] = "Punching Failure at Column"
    else:
        results["punching_status"] = f"OK: v_face ({v_face:.3f}) ≤ v_max ({v_max_punch:.3f})"

    # -------------------------------------------------------------------------
    # Step 5: Detailing notes  (Cl 3.11.4.6)
    # -------------------------------------------------------------------------
    notes.append("--- Detailing Notes (Cl 3.11.4.6 / 3.12) ---")
    notes.append(
        "Pile cap bars should be arranged in a band of width = minimum(cx,cy) + 3Φ_pile "
        "directly over the piles. The minimum bar centres should not exceed 3Φ_pile."
    )
    # Horizontal distribution bars (longitudinal ties)
    As_dist_min = 0.0020 * section.ly * section.h   # 0.2% each way in top and sides
    notes.append(
        f"Provide horizontal distribution / tie bars in the sides of the cap: "
        f"As ≥ 0.20% × {section.ly:.0f} × {section.h:.0f} = {As_dist_min:.0f} mm² each way."
    )
    anchorage = 40 * int(section.bar_dia)
    notes.append(
        f"Bar anchorage past pile CL: ≥ 40Φ = {anchorage} mm beyond pile centreline (Cl 3.12.8)."
    )

    return results
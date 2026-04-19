"""
BS EN 1992-1-1:2004  –  Foundation Design
=========================================
Fully-checked design functions for Eurocode 2 (EC2) foundation design:
  * ``design_pad_footing``  — Isolated pad footing flexure and shear checks.
  * ``design_pile_cap``     — Pile cap design using truss analogy.

These functions are designed to be used as tools for structural engineering AI models.
"""

from __future__ import annotations

import math
from typing import Optional

from models.ec2.footing import PadFooting, PileCap
from core.design.rc.eurocode2.formulas import (
    calculate_k,
    calculate_lever_arm,
    calculate_singly_reinforced,
    calculate_VRd_c,
)
from core.design.rc.common.select_reinforcement import select_slab_reinforcement


def check_reinforcement_limits_ec2(As_prov: float, As_min: float, As_max: float, label: str) -> dict:
    """
    Check if the provided reinforcement area is within the EC2 minimum and maximum limits.

    Parameters
    ----------
    As_prov : float
        The area of reinforcement provided (mm2).
    As_min : float
        The minimum required area of reinforcement (mm2) per EC2 Cl 9.2.1.1.
    As_max : float
        The maximum allowed area of reinforcement (mm2) per EC2 Cl 9.2.1.1.
    label : str
        A descriptive label for the reinforcement being checked (e.g., 'x-direction').

    Returns
    -------
    dict
        A dictionary containing the check 'status' ('OK' or 'FAIL') and a descriptive 'note'.
    """
    if As_prov < As_min:
        return {
            "status": "FAIL",
            "note": f"{label}: As_prov ({As_prov:.1f}) < As_min ({As_min:.1f})",
        }
    if As_prov > As_max:
        return {
            "status": "FAIL",
            "note": f"{label}: As_prov ({As_prov:.1f}) > As_max ({As_max:.1f})",
        }
    return {
        "status": "OK",
        "note": f"{label}: As limits OK ({As_min:.1f} <= {As_prov:.1f} <= {As_max:.1f})",
    }


def design_pad_footing(
    section: PadFooting,
    N_Ed: float,                    # Factored axial column load (N)
    Mx_Ed: float = 0.0,             # Factored moment about x-axis (N·mm)
    My_Ed: float = 0.0,             # Factored moment about y-axis (N·mm)
) -> dict:
    """
    Design an isolated rectangular pad footing according to BS EN 1992-1-1 (EC2).

    The design checks flexure at the column face, beam shear at distance 'd' from the column face,
    and punching shear at a 2.0d perimeter.

    Parameters
    ----------
    section : PadFooting
        The pad footing geometry and material model.
    N_Ed : float
        The ultimate design axial load from the column (N).
    Mx_Ed : float
        The ultimate design moment about the x-axis at the column base (N·mm).
    My_Ed : float
        The ultimate design moment about the y-axis at the column base (N·mm).

    Returns
    -------
    dict
        A dictionary containing:
            - status: Overall design status ('OK', 'Shear Failure', etc.).
            - As_req_x, As_req_y: Required reinforcement area (mm2/m).
            - reinforcement_x, reinforcement_y: Selected bar descriptions.
            - shear_x_status, shear_y_status: Status of beam shear checks.
            - punching_status: Status of the punching shear check.
            - notes, warnings: Detailed calculation logs and alerts.
    """
    notes: list[str] = []
    warnings: list[str] = []
    results: dict = {"status": "OK", "notes": notes, "warnings": warnings}

    notes.append(section.summary())
    notes.append(
        f"Design actions: N_Ed = {N_Ed/1e3:.1f} kN, Mx_Ed = {Mx_Ed/1e6:.1f} kN·m, "
        f"My_Ed = {My_Ed/1e6:.1f} kN·m  (EC2)"
    )

    lx = section.lx
    ly = section.ly
    h  = section.h
    d  = section.d
    fck = section.fck
    fyk = section.fyk
    cx = section.column_cx
    cy = section.column_cy

    # 1. Bearing Pressure
    A_plan    = lx * ly
    q_uni     = N_Ed / A_plan
    q_x_ecc  = 6.0 * Mx_Ed / (lx * ly ** 2) if Mx_Ed != 0 else 0
    q_y_ecc  = 6.0 * My_Ed / (lx ** 2 * ly) if My_Ed != 0 else 0
    q_max    = q_uni + q_x_ecc + q_y_ecc
    q_min    = q_uni - q_x_ecc - q_y_ecc

    results["q_max_kNm2"] = round(q_max * 1e3, 2)
    results["q_min_kNm2"] = round(q_min * 1e3, 2)
    notes.append(f"Bearing pressure: q_max = {q_max*1e3:.2f} kN/m², q_min = {q_min*1e3:.2f} kN/m²")

    if q_min < 0:
        warnings.append("q_min < 0: footing in partial uplift. Continues with q_max.")

    q = q_max

    # 2. Cantilever Moments
    a_x = (lx - cx) / 2.0
    a_y = (ly - cy) / 2.0

    M_x = q * a_x ** 2 / 2.0
    M_y = q * a_y ** 2 / 2.0
    M_x_pm = M_x * 1000.0
    M_y_pm = M_y * 1000.0

    results["cantilever_moments_kNm_per_m"] = {
        "Mx_at_column_face": round(M_x_pm / 1e6, 2),
        "My_at_column_face": round(M_y_pm / 1e6, 2),
    }

    # 3. Flexural Design
    def _flex_design(M_pm: float, label: str) -> tuple[float, dict, list, list]:
        _n, _w = [], []
        b = 1000.0
        k_res = calculate_k(M_pm, fck, b, d)
        K = k_res["value"]
        _n.append(k_res["note"])
        if K > 0.167:
            _w.append(f"{label}: K > K_lim (0.167). Section inadequate.")
            return None, None, _n, _w
        z_res = calculate_lever_arm(d, K)
        _n.append(z_res["note"])
        As_val = calculate_singly_reinforced(M_pm, fyk, z_res["value"])["value"]
        As_design = max(As_val, section.As_min)
        bars = select_slab_reinforcement(As_design, d, h, fyk)
        _n.append(f"{label}: As_req = {As_val:.1f} mm²/m → {bars['description']}")
        if bars["warning"]:
            _w.append(bars["warning"])
        return As_val, bars, _n, _w

    As_x, bars_x, nx, wx = _flex_design(M_x_pm, "x-direction")
    notes.extend(nx); warnings.extend(wx)
    if As_x is None:
        results["status"] = "Section Inadequate (x-flexure)"
        return results
    results["As_req_x"] = round(As_x, 2)
    results["As_prov_x"] = bars_x["As_prov"]
    results["reinforcement_x"] = bars_x["description"]

    As_y, bars_y, ny, wy = _flex_design(M_y_pm, "y-direction")
    notes.extend(ny); warnings.extend(wy)
    if As_y is None:
        results["status"] = "Section Inadequate (y-flexure)"
        return results
    results["As_req_y"] = round(As_y, 2)
    results["As_prov_y"] = bars_y["As_prov"]
    results["reinforcement_y"] = bars_y["description"]

    for label, As_prov in [("x", bars_x["As_prov"]), ("y", bars_y["As_prov"])]:
        lim_res = check_reinforcement_limits_ec2(As_prov, section.As_min, section.As_max, label)
        notes.append(lim_res["note"])

    # 4. Beam Shear
    def _beam_shear_check(a_crit: float, As_prov: float, label: str) -> str:
        _n, _w = [], []
        projection = a_crit - d
        if projection <= 0:
            return "OK (inside column)"
        V_strip = q * projection * 1000.0
        v_shear = V_strip / (1000.0 * d)
        
        vrdc_res = calculate_VRd_c(As_prov, fck, 1000.0, d)
        _n.append(vrdc_res["note"])
        notes.extend(_n)
        if V_strip > vrdc_res["value"]:
            return f"FAIL: VEd ({V_strip/1e3:.1f} kN) > VRd,c ({vrdc_res['value']/1e3:.1f} kN)"
        return "OK"

    shear_x = _beam_shear_check(a_x, bars_x["As_prov"], "Beam shear x")
    shear_y = _beam_shear_check(a_y, bars_y["As_prov"], "Beam shear y")
    results["shear_x_status"] = shear_x
    results["shear_y_status"] = shear_y
    if "FAIL" in shear_x or "FAIL" in shear_y:
        results["status"] = "Shear Failure"

    # 5. Punching Shear
    u1 = 2.0 * (cx + cy) + 4.0 * math.pi * d
    notes.append(f"Critical 2d perimeter: u1 = {u1:.0f} mm (EC2 Cl 6.4.2)")

    cx_punch = cx + 4.0 * d
    cy_punch = cy + 4.0 * d
    area_punch = cx_punch * cy_punch - (4.0 - math.pi) * (2.0 * d)**2
    
    V_punch_net = max(N_Ed - q * area_punch, 0.0)
    beta = 1.15 if (Mx_Ed != 0 or My_Ed != 0) else 1.0
    v_Ed_punch = beta * V_punch_net / (u1 * d)
    results["v_punch"] = round(v_Ed_punch, 4)

    As_punch_avg = (bars_x["As_prov"] + bars_y["As_prov"]) / 2.0
    vrdc_punch_res = calculate_VRd_c(As_punch_avg, fck, 1000.0, d)
    v_Rd_c_punch = vrdc_punch_res["value"] / (1000.0 * d)

    if v_Ed_punch > v_Rd_c_punch:
        results["punching_status"] = f"FAIL: v_Ed ({v_Ed_punch:.3f}) > VRd,c ({v_Rd_c_punch:.3f})"
        if results["status"] == "OK":
            results["status"] = "Punching Failure"
    else:
        results["punching_status"] = f"OK: v_Ed ({v_Ed_punch:.3f}) <= VRd,c ({v_Rd_c_punch:.3f})"

    return results


def design_pile_cap(
    section: PileCap,
    N_Ed: float,        # Factored axial column load (N)
    Mx_Ed: float = 0.0, # Factored moment about x-axis (N·mm)
) -> dict:
    """
    Design a pile cap using the truss analogy method according to BS EN 1992-1-1 (EC2).

    Parameters
    ----------
    section : PileCap
        The pile cap geometry and material model.
    N_Ed : float
        The ultimate design axial load from the column (N).
    Mx_Ed : float
        The ultimate design moment about the x-axis (N·mm). Only used for 2-pile caps currently.

    Returns
    -------
    dict
        A dictionary containing:
            - status: Overall design status ('OK', 'Shear Failure', etc.).
            - As_req: Required tension tie reinforcement (mm2).
            - reinforcement_description: Selected bar description.
            - shear_status: Status of the enhanced shear check.
            - punching_status: Status of the punching shear check at the column face.
            - notes, warnings: Detailed calculation logs and alerts.
    """
    notes: list[str] = []
    warnings: list[str] = []
    results: dict = {"status": "OK", "notes": notes, "warnings": warnings}

    notes.append(section.summary())
    notes.append(f"Design actions: N_Ed = {N_Ed/1e3:.1f} kN  (EC2 truss analogy)")

    d             = section.d
    fck           = section.fck
    fyk           = section.fyk
    pile_s        = section.pile_spacing
    pile_dia      = section.pile_dia
    num_piles     = section.num_piles
    cx            = section.column_cx
    cy            = section.column_cy

    # 1. Pile Reactions
    R_pile = N_Ed / num_piles
    if abs(Mx_Ed) > 0 and num_piles == 2:
        R_pile_max = N_Ed / 2.0 + abs(Mx_Ed) / pile_s
        R_pile = R_pile_max

    # 2. Tension Tie (Truss Analogy)
    z = d - pile_dia / 4.0
    if z <= 0:
        z = 0.8 * d

    l_arm = pile_s / 2.0
    T = R_pile * l_arm / z
    As_req = T / (fyk / 1.15)
    As_req = max(As_req, section.As_min)

    results["As_req"] = round(As_req, 2)
    bars = select_slab_reinforcement(As_req, d, section.h, fyk)
    results["As_prov"] = bars["As_prov"]
    results["reinforcement_description"] = bars["description"]
    
    lim_res = check_reinforcement_limits_ec2(bars["As_prov"], section.As_min, section.As_max, "tension")
    notes.append(lim_res["note"])

    # 3. Shear (Enhanced)
    av = (pile_s / 2.0) - (0.3 * pile_dia) - (cx / 2.0)
    if av <= 0:
        results["shear_status"] = "OK (critical section inside column)"
    else:
        v_shear_force = R_pile
        vrdc_res = calculate_VRd_c(bars["As_prov"], fck, section.ly, d)
        vrdc = vrdc_res["value"]
        
        av_eff = max(av, 0.5 * d)
        enhancement = min(2.0 * d / av_eff, 4.0) 
        vrdc_enhanced = vrdc * enhancement
        
        if v_shear_force > vrdc_enhanced:
            results["shear_status"] = f"FAIL: V_Ed ({v_shear_force/1e3:.1f} kN) > VRd,c_enhanced ({vrdc_enhanced/1e3:.1f} kN)"
            results["status"] = "Shear Failure"
        else:
            results["shear_status"] = "OK"

    # 4. Punching at Column Face
    u0 = 2.0 * (cx + cy)
    v_Ed_face = N_Ed / (u0 * d)
    nu = 0.6 * (1 - fck / 250)
    fcd = 0.85 * fck / 1.5
    v_Rd_max = 0.5 * nu * fcd
    
    if v_Ed_face > v_Rd_max:
        results["punching_status"] = f"FAIL: v_Ed ({v_Ed_face:.3f}) > v_Rd,max ({v_Rd_max:.3f}) at face"
        if results["status"] == "OK":
            results["status"] = "Punching Failure"
    else:
        results["punching_status"] = "OK"

    return results

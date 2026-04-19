"""
BS EN 1992-1-1:2004 (EC2)  –  Special Slab Design  (Ribbed, Waffle & Flat Slabs)
=================================================================================
Handles design of special slab configurations under EC2:

  1. **Ribbed / Waffle Slabs** (Cl 9.3.3) — one-way or two-way spanning T-section ribs.
  2. **Flat Slabs** (Cl 9.4) — solid slabs supported directly on columns with or 
     without drop panels, designed using strip distribution and checked for punching shear (Cl 6.4).

Design Sequence
---------------
Ribbed / Waffle:
  1. Geometric checks (topping thickness, clear spacing).
  2. Flanged-beam flexural design per rib (Web = rib width, Flange = rib spacing).
  3. Neutral axis check.
  4. Bar selection.
  5. Shear check per rib against VRd,c (Cl 6.2.2).
  6. Deflection check for flanged sections (Cl 7.4.2).

Flat Slab:
  1. Global panel moment calculation (often via equivalent frame or simplified rules).
  2. Distribution of total moment into Column Strip and Middle Strip.
  3. Flexural design of each strip per metre width.
  4. Deflection check on the most critical strip.
  5. Punching shear check at column face and 2d control perimeter (Cl 6.4).
"""

from __future__ import annotations

import math
from typing import Optional

from models.ec2.slab import EC2RibbedSection, EC2FlatSlabSection
from core.design.rc.eurocode2.formulas import (
    calculate_k,
    calculate_lever_arm,
    calculate_singly_reinforced,
    calculate_flanged_beam,
    calculate_VRd_c,
    calculate_punching_VRd_c,
    calculate_punching_v_Ed,
    calculate_deflection_limit,
    crack_control_spacing,
)
from core.design.rc.common.select_reinforcement import (
    select_beam_reinforcement,
    select_slab_reinforcement,
)


# ===========================================================================
# 1. Ribbed / Waffle Slab Design
# ===========================================================================

def design_ribbed_slab(
    section: EC2RibbedSection,
    M_rib: float,           # Design moment per rib (N·mm)
    V_rib: float,           # Design shear force per rib (N)
    span: float,            # Effective span (mm)
    delta: float = 1.0,     # Moment redistribution ratio
    sigma_s_qp: Optional[float] = None, # quasi-permanent stress for crack control
) -> dict:
    """
    Design a single rib of a ribbed or waffle slab per EC2.

    The rib is treated as a flanged section (T-beam).

    Parameters
    ----------
    section    : ``EC2RibbedSection`` instance.
    M_rib      : Design ultimate moment per rib (N·mm).
    V_rib      : Design ultimate shear per rib (N).
    span       : Effective span of the rib (mm).
    delta      : Moment redistribution ratio (default 1.0).
    sigma_s_qp : Serviceability steel stress (N/mm²) for cracking check.

    Returns
    -------
    dict: Complete design results including required As, provided bars, 
          deflection/shear/cracking status, and calculation notes.
    """
    notes: list[str] = []
    warnings: list[str] = []
    results: dict = {"status": "OK", "notes": notes, "warnings": warnings}

    notes.append(section.summary())
    notes.append(
        f"Design actions per rib: M = {M_rib/1e6:.2f} kN·m, V = {V_rib/1e3:.2f} kN"
    )

    b_f = section.rib_spacing
    b_w = section.rib_width
    h_f = section.topping_thickness
    d   = section.d_x
    fck = section.fck
    fyk = section.fyk
    
    # 1. Geometric checks
    min_topping = max(50.0, 0.1 * section.clear_rib_spacing)
    if h_f < min_topping:
        warnings.append(f"Topping ({h_f} mm) < min {min_topping:.0f} mm (EC2 Cl 9.3.3(2)).")
    notes.append(f"Topping thickness check: {h_f} mm ≥ min {min_topping:.0f} mm.")

    # 2. Flexural Design
    notes.append("--- Flanged-beam flexural design ---")
    d_prime = section.cover + section.bar_dia_x / 2.0  # approximate comp centroid if needed
    fl_res = calculate_flanged_beam(
        M=M_rib, fck=fck, fyk=fyk,
        bw=b_w, bf=b_f, d=d, hf=h_f, d_prime=d_prime, delta=delta
    )
    notes.append(fl_res["note"])
    if "FAIL" in fl_res["note"]:
        results["status"] = "Flexure Failure"
    
    As_req = fl_res["As_req"]
    As_design = max(As_req, section.As_rib_min)

    # 3. Bar Selection
    link_dia = 8.0  # Assumed min link dia
    bars = select_beam_reinforcement(
        As_req=As_design, b_available=b_w, cover=section.cover, link_dia=link_dia
    )
    results["As_req"] = round(As_req, 2)
    results["As_prov"] = bars["As_prov"]
    results["reinforcement_description"] = bars["description"]
    if bars["warning"]:
        warnings.append(bars["warning"])
    notes.append(f"Main rib steel: {bars['description']} (As_prov = {bars['As_prov']:.1f} mm²)")

    # 4. Shear Check
    notes.append("--- Shear Check (EC2 Cl 6.2.2) ---")
    vrdc_res = calculate_VRd_c(bars["As_prov"], fck, b_w, d)
    VRd_c = vrdc_res["value"]
    notes.append(vrdc_res["note"])
    if V_rib > VRd_c:
        results["shear_status"] = f"FAIL: V_Ed={V_rib/1e3:.1f} kN > VRd,c={VRd_c/1e3:.1f} kN"
        warnings.append("Shear exceeds concrete capacity. Increase rib dimensions or provide shear links.")
        if results["status"] == "OK":
            results["status"] = "Shear Failure"
    else:
        results["shear_status"] = f"OK: V_Ed={V_rib/1e3:.1f} kN ≤ VRd,c={VRd_c/1e3:.1f} kN"

    # 5. Deflection Check
    notes.append("--- Deflection Check (EC2 Cl 7.4.2) ---")
    rho   = As_req / (b_w * d)  # Note: rho for flanged beams uses bw
    rho_0 = math.sqrt(fck) / 1000.0
    b_t_bw = b_f / b_w
    defl_res = calculate_deflection_limit(
        fck=fck, fyk=fyk, rho=rho, rho_0=rho_0,
        is_end_span=section.is_end_span,
        support_condition=section.support_condition,
        b_t_bw=b_t_bw
    )
    allow_ld = defl_res["value"]
    actual_ld = span / d
    if actual_ld > allow_ld:
        results["deflection_check"] = "FAIL"
        warnings.append(f"Deflection FAIL: L/d = {actual_ld:.1f} > allowable {allow_ld:.1f}.")
        if results["status"] == "OK":
            results["status"] = "Deflection Failure"
    else:
        results["deflection_check"] = "OK"
    notes.append(defl_res["note"])

    # 6. Crack Control
    if sigma_s_qp is None:
        sigma_s_qp = (fyk / 1.15) * (As_req / bars["As_prov"]) * 0.7  # Approximate quasi-permanent
    crack_res = crack_control_spacing(sigma_s_qp)
    notes.append(crack_res["note"])
    results["crack_spacing_max_mm"] = crack_res["max_spacing_mm"]

    # 7. Topping Mesh
    As_mesh_min = 0.0013 * 1000.0 * h_f  # Conservative min steel for topping
    mesh = select_slab_reinforcement(As_mesh_min, h_f/2.0, h_f, fyk)
    results["topping_mesh"] = mesh["description"]
    notes.append(f"Topping mesh: As_min = {As_mesh_min:.0f} mm²/m → {mesh['description']}")

    return results


# ===========================================================================
# 2. Flat Slab Design
# ===========================================================================

# Standard distribution factors for flat slabs (Similar to BS8110 / IStructE EC2 Manual)
FLAT_SLAB_DISTRIBUTION = {
    "interior": {
        "hogging": {"CS": 0.75, "MS": 0.25},
        "sagging": {"CS": 0.55, "MS": 0.45},
    },
    "edge": {
        "hogging": {"CS": 0.80, "MS": 0.20},
        "sagging": {"CS": 0.60, "MS": 0.40},
    },
    "corner": {
        "hogging": {"CS": 0.80, "MS": 0.20},
        "sagging": {"CS": 0.60, "MS": 0.40},
    },
}

def calculate_flat_slab_moments(
    section: EC2FlatSlabSection,
    n_udl: float,   # Design UDL (N/mm²)
) -> dict:
    """
    Compute total design moment Mt and distribute into column / middle strips.

    Using a simplified equivalent frame / prescriptive coefficient approach:
        Mt = 0.125 × n × L2 × L_eff²
    Distributes into Column Strip (CS) and Middle Strip (MS) moments using 
    standard fractions.

    Parameters
    ----------
    section : ``EC2FlatSlabSection`` instance.
    n_udl   : Factored design load (N/mm²).

    Returns
    -------
    dict: Strip moments (per metre width) and effective parameters.
    """
    notes: list[str] = []
    warnings: list[str] = []

    L1 = section.lx
    L2 = section.ly
    hc = section.column_c

    # Effective span (simplified equivalent to L - 2*hc/3)
    L_eff = L1 - (2.0 * hc / 3.0)
    L_eff_min = 0.65 * L1
    if L_eff < L_eff_min:
        L_eff = L_eff_min
    notes.append(f"Effective span L_eff = {L_eff:.0f} mm (minimum 0.65L)")

    Mt = 0.125 * n_udl * L2 * (L_eff ** 2)
    notes.append(f"Total panel moment Mt = {Mt/1e6:.2f} kN·m")

    # Assuming internal span proportioning: 65% hogging, 35% sagging
    M_hog_total = 0.65 * Mt
    M_sag_total = 0.35 * Mt
    
    CS_width = min(L1, L2)
    MS_width = max(L2 - CS_width, 0.001)

    dist = FLAT_SLAB_DISTRIBUTION.get(section.edge_condition, FLAT_SLAB_DISTRIBUTION["interior"])
    
    CS_hog = (dist["hogging"]["CS"] * M_hog_total) / CS_width
    MS_hog = (dist["hogging"]["MS"] * M_hog_total) / MS_width
    CS_sag = (dist["sagging"]["CS"] * M_sag_total) / CS_width
    MS_sag = (dist["sagging"]["MS"] * M_sag_total) / MS_width

    notes.append(
        f"Moment distribution to strips per metre width ({section.edge_condition} panel):\n"
        f"  Column Strip width: {CS_width:.0f} mm, Middle Strip width: {MS_width:.0f} mm\n"
        f"  CS Hogging: {CS_hog/1e6:.2f} kN·m/m,  MS Hogging: {MS_hog/1e6:.2f} kN·m/m\n"
        f"  CS Sagging: {CS_sag/1e6:.2f} kN·m/m,  MS Sagging: {MS_sag/1e6:.2f} kN·m/m"
    )

    return {
        "Mt_kNm": round(Mt/1e6, 2),
        "CS_hogging_pm": CS_hog,
        "MS_hogging_pm": MS_hog,
        "CS_sagging_pm": CS_sag,
        "MS_sagging_pm": MS_sag,
        "CS_width_mm": CS_width,
        "MS_width_mm": MS_width,
        "notes": notes,
        "warnings": warnings,
    }


def _design_flat_strip(M_pm: float, section: EC2FlatSlabSection, label: str, is_drop: bool = False) -> dict:
    notes = []
    warnings = []
    d = section.d_drop if is_drop else section.d_x

    if M_pm <= 0:
        bars = select_slab_reinforcement(section.As_min, d, section.h, section.fyk)
        return {"As_req": 0.0, "bars": bars, "notes": [f"{label}: Minimum steel."], "warnings": []}

    b = 1000.0
    k_res = calculate_k(M_pm, section.fck, b, d)
    K = k_res["value"]
    notes.append(k_res["note"])

    if K > section.K_lim:
        warnings.append(f"{label}: K > K_lim. Compression steel required or section too shallow.")
        return {"As_req": None, "bars": None, "notes": notes, "warnings": warnings}

    z_res = calculate_lever_arm(d, K, section.delta)
    notes.append(z_res["note"])
    As_req = calculate_singly_reinforced(M_pm, section.fyk, z_res["value"])["value"]
    As_design = max(As_req, section.As_min)

    h_eff = (section.h + section.drop_thickness_extra) if is_drop else section.h
    bars = select_slab_reinforcement(As_design, d, h_eff, section.fyk)
    
    notes.append(f"{label}: As_req = {As_req:.1f} mm²/m → {bars['description']}")
    return {"As_req": As_req, "bars": bars, "notes": notes, "warnings": warnings}


def design_flat_slab_punching(
    section: EC2FlatSlabSection,
    V_Ed: float,    # Total column reaction (N)
) -> dict:
    """
    Punching shear check per EC2 Cl 6.4.

    Parameters
    ----------
    section : ``EC2FlatSlabSection`` instance.
    V_Ed    : Total design shear force at the column (N).

    Returns
    -------
    dict: Punching check output including status and resistances.
    """
    notes = []
    warnings = []
    status = "OK"

    # Effective shear V_eff = β * V_Ed
    beta = section.beta_ec2
    V_eff = beta * V_Ed

    d = section.d_drop if (section.is_drop_panel and section.drop_thickness_extra > 0) else section.d_x
    fck = section.fck
    hc = section.column_c

    # 1. Column Face Perimeter (u0)
    if section.is_circular_col:
        u0 = math.pi * hc
    else:
        u0 = 4.0 * hc
    
    vEd_face = V_eff / (u0 * d)
    # vRd_max (Cl 6.4.5) ≈ 0.5 * v * fcd
    nu = 0.6 * (1.0 - fck / 250.0)
    fcd = section.fcd
    vRd_max = 0.5 * nu * fcd
    
    notes.append(f"Column face u0 = {u0:.0f} mm: vEd = {vEd_face:.3f} N/mm² vs vRd_max = {vRd_max:.3f} N/mm²")
    if vEd_face > vRd_max:
        status = "FAIL: Punching shear at face exceeds vRd,max (crushing limit)."
        warnings.append(f"vEd ({vEd_face:.3f}) > vRd_max ({vRd_max:.3f}) at column face.")

    # 2. Control Perimeter at 2d (u1)
    if section.is_circular_col:
        u1 = math.pi * (hc + 4.0 * d)
    else:
        u1 = 4.0 * hc + 2.0 * math.pi * (2.0 * d)

    vEd_u1_res = calculate_punching_v_Ed(V_Ed, beta, u1, d)
    vEd_u1 = vEd_u1_res["value"]
    notes.append(f"Control perimeter 2d (u1) = {u1:.0f} mm: " + vEd_u1_res["note"])

    rho_l = 0.0075  # Assumed 0.75% avg tension steel
    vrdc_res = calculate_punching_VRd_c(fck, d, rho_l)
    vRd_c = vrdc_res["value"]
    notes.append(vrdc_res["note"])

    if vEd_u1 > vRd_c:
        if status == "OK":
            status = "Shear Reinforcement Required"
        warnings.append(f"vEd ({vEd_u1:.3f}) > vRd,c ({vRd_c:.3f}) at control perimeter. Punching shear reinforcement is required.")
    else:
        notes.append(f"Punching shear at 2d: vEd ({vEd_u1:.3f}) ≤ vRd,c ({vRd_c:.3f}). OK.")

    return {
        "status": status,
        "vEd_face": round(vEd_face, 4),
        "vRd_max": round(vRd_max, 4),
        "vEd_u1": round(vEd_u1, 4),
        "vRd_c": round(vRd_c, 4),
        "perimeters": {"u0": round(u0, 1), "u1": round(u1, 1)},
        "notes": notes,
        "warnings": warnings,
    }


def design_flat_slab(
    section: EC2FlatSlabSection,
    n_udl: float,
) -> dict:
    """
    Full EC2 flat slab design.

    Parameters
    ----------
    section : ``EC2FlatSlabSection`` instance.
    n_udl   : Factored design UDL (N/mm²).

    Returns
    -------
    dict: Complete flat slab design output.
    """
    notes = []
    warnings = []
    results = {"status": "OK", "notes": notes, "warnings": warnings}

    notes.append(section.summary())
    notes.append(f"Design UDL = {n_udl * 1e3:.2f} kN/m²")

    # Moments
    mom_res = calculate_flat_slab_moments(section, n_udl)
    notes.extend(mom_res["notes"])
    warnings.extend(mom_res["warnings"])

    # Strip Flexure
    for label, M_pm in [
        ("CS_hogging", mom_res["CS_hogging_pm"]),
        ("MS_hogging", mom_res["MS_hogging_pm"]),
        ("CS_sagging", mom_res["CS_sagging_pm"]),
        ("MS_sagging", mom_res["MS_sagging_pm"]),
    ]:
        is_drop = (section.is_drop_panel and "hogging" in label)
        sd = _design_flat_strip(M_pm, section, label, is_drop)
        notes.extend(sd["notes"])
        warnings.extend(sd["warnings"])
        if sd["As_req"] is None:
            results["status"] = f"Flexure Failure ({label})"
        if sd["bars"]:
            results[f"{label}_steel"] = sd["bars"]["description"]

    # Deflection Check
    defl_res = calculate_deflection_limit(
        fck=section.fck, fyk=section.fyk,
        rho=0.005,  # approximate for flat slab
        rho_0=math.sqrt(section.fck)/1000.0,
        is_end_span=False, support_condition="continuous"
    )
    # factor for flat slabs (Table 7.4N) K=1.2
    allowable_ld = defl_res["basic_ld"] * 1.2
    actual_ld = section.lx / section.d_x
    if actual_ld > allowable_ld:
        warnings.append(f"Deflection FAIL: actual L/d {actual_ld:.1f} > {allowable_ld:.1f}")
        results["deflection_check"] = "FAIL"
    else:
        results["deflection_check"] = "OK"

    # Punching Check
    V_Ed = n_udl * section.lx * section.ly
    punch_res = design_flat_slab_punching(section, V_Ed)
    results["punching_shear"] = punch_res
    notes.extend(punch_res["notes"])
    warnings.extend(punch_res["warnings"])
    if punch_res["status"] != "OK":
        if results["status"] == "OK":
            results["status"] = punch_res["status"]

    return results


# ===========================================================================
# 3. Unified Dispatcher
# ===========================================================================

def calculate_special_slab_reinforcement(
    section: EC2RibbedSection | EC2FlatSlabSection,
    n_udl: float,
    M_rib: Optional[float] = None,
    V_rib: Optional[float] = None,
    span: Optional[float] = None,
) -> dict:
    """
    Unified dispatcher for EC2 special slab design.

    Parameters
    ----------
    section : Slab section instance (Ribbed or Flat).
    n_udl   : Factored design UDL (N/mm²).
    M_rib   : Design moment per rib (N·mm) - for ribbed/waffle slabs.
    V_rib   : Design shear per rib (N) - for ribbed/waffle slabs.
    span    : Effective span (mm) - for ribbed/waffle slabs.

    Returns
    -------
    dict: Results of the appropriate slab design function.
    """
    if isinstance(section, EC2RibbedSection):
        if M_rib is None or V_rib is None or span is None:
            raise ValueError(
                "M_rib, V_rib, and span must be provided for ribbed/waffle slabs."
            )
        return design_ribbed_slab(section, M_rib, V_rib, span)
    elif isinstance(section, EC2FlatSlabSection):
        return design_flat_slab(section, n_udl)
    else:
        raise TypeError(f"Section must be EC2RibbedSection or EC2FlatSlabSection, got {type(section).__name__}.")

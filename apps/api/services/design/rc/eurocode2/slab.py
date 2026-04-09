"""
BS EN 1992-1-1:2004 (EC2)  –  Solid Slab Design  (One-Way & Two-Way)
======================================================================
``calculate_slab_reinforcement`` is the single entry point.

Imports
-------
  * ``EC2SlabSection``  from ``models.ec2_slab``
  * Formulas            from ``services.design.rc.eurocode2.formulas``
  * Bar selector        from ``services.design.rc.common.select_reinforcement``

Design sequence — One-Way Slab (EC2 Cl 9.3)
---------------------------------------------
1.  Section summary and design moment.
2.  Bending design (K / z / As) — same approach as beam, 1m strip.
3.  Minimum reinforcement check (Cl 9.3.1.1).
4.  Secondary (transverse distribution) reinforcement (Cl 9.3.1.1(2)):
       As_sec ≥ 20% of main As.
5.  Deflection check — span/d ratio (Cl 7.4.2 Eq. 7.16).
6.  Shear check VRd,c (Cl 6.2.2) — normally slabs are designed without
    shear reinforcement; a warning is issued if V_Ed > VRd,c.
7.  Crack spacing table check (Cl 7.3.3 Table 7.3N).

Design sequence — Two-Way Slab (EC2 Cl 9.3)
---------------------------------------------
1.  Coefficient lookup (IStructE EC2 Manual Table A3 via formulas.py).
2.  Sagging moments:   m_sx = α_sx·n·lx²,   m_sy = α_sy·n·lx²
    Hogging moments:   m_hx = β_sx·n·lx²,   m_hy = β_sy·n·lx²
3.  Short-span and long-span flexural design.
4.  x-direction and y-direction deflection checks.
5.  Shear check at column/wall support.
6.  Torsion reinforcement at corners of simply supported panels (Cl 9.3.2).

Modularity
----------
No formulae in this file. All physics in ``formulas.py``.
"""

from __future__ import annotations

import math
from typing import Optional

from models.ec2.slab import EC2SlabSection
from services.design.rc.common.select_reinforcement import select_slab_reinforcement
from services.design.rc.eurocode2.formulas import (
    calculate_k,
    calculate_lever_arm,
    calculate_singly_reinforced,
    calculate_doubly_reinforced,
    calculate_VRd_c,
    calculate_deflection_limit,
    crack_control_spacing,
    get_two_way_coefficients,
)


# ===========================================================================
# Internal helper — design a 1 m strip for a given moment
# ===========================================================================

def _design_strip(
    M_pm: float,         # Design moment per metre (N·mm/m), positive = sagging
    d: float,            # Effective depth (mm)
    section: EC2SlabSection,
    label: str,
    As_min: float,
) -> dict:
    """
    Flexural design of a 1m slab strip.

    Returns dict with As_req, bars, notes, warnings.
    """
    notes, warnings = [], []
    b = 1000.0

    if M_pm <= 0:
        bars = select_slab_reinforcement(As_min, d, section.h, section.fyk)
        return {"As_req": 0.0, "bars": bars, "notes": [f"{label}: M=0 — minimum steel."], "warnings": []}

    k_res = calculate_k(M_pm, section.fck, b, d)
    K = k_res["value"]
    notes.append(k_res["note"])

    if K > section.K_lim:
        warnings.append(f"{label}: K ({K:.4f}) > K_lim ({section.K_lim:.3f}). Increase slab depth.")
        dr = calculate_doubly_reinforced(M_pm, section.fck, section.fyk, b, d,
                                         section.cover + section.bar_dia_x, section.delta)
        As_req = dr["As"]
        notes.append(dr["note"])
    else:
        z_res = calculate_lever_arm(d, K, section.delta)
        notes.append(z_res["note"])
        As_req = calculate_singly_reinforced(M_pm, section.fyk, z_res["value"])["value"]

    As_design = max(As_req, As_min)
    bars = select_slab_reinforcement(As_design, d, section.h, section.fyk)
    if bars["warning"]:
        warnings.append(bars["warning"])
    notes.append(f"{label}: As_req={As_req:.0f} mm²/m → {bars['description']}")
    return {"As_req": As_req, "bars": bars, "notes": notes, "warnings": warnings}


# ===========================================================================
# One-way slab design
# ===========================================================================

def _design_one_way(section: EC2SlabSection, n: float, V_Ed: float,
                    sigma_s_qp: Optional[float], notes: list, warnings: list) -> dict:
    """Design a one-way slab strip. Returns partial results dict."""
    results = {}
    d = section.d_x
    span = section.lx

    # --- Bending moment ---
    if section.support_condition == "simple":
        M_Ed = n * span ** 2 / 8.0
    elif section.support_condition == "cantilever":
        M_Ed = n * span ** 2 / 2.0
    else:  # continuous — use 0.125 wl² as sagging, 0.086×... reserved for coefficients
        M_Ed = n * span ** 2 / 10.0   # conservative for continuous end span
    notes.append(
        f"One-way slab ({section.support_condition}): M_Ed = n·L²/coeff = "
        f"{n*1e3:.3f}×{span:.0f}²/coeff = {M_Ed/1e6:.2f} kN·m/m"
    )

    sd = _design_strip(M_Ed, d, section, "Main (x)", section.As_min)
    notes.extend(sd["notes"]); warnings.extend(sd["warnings"])
    results["As_req"]         = round(sd["As_req"], 2)
    results["As_prov"]        = sd["bars"]["As_prov"]
    results["main_steel"]     = sd["bars"]["description"]

    # Secondary (distribution) steel — Cl 9.3.1.1(2): ≥ 20% of main
    As_sec_min = max(0.20 * sd["bars"]["As_prov"], section.As_min * 0.20)
    d_sec = section.d_y
    bars_sec = select_slab_reinforcement(As_sec_min, d_sec, section.h, section.fyk)
    results["secondary_steel"] = bars_sec["description"]
    notes.append(
        f"Secondary (transverse) steel: ≥ 20% of main = {As_sec_min:.0f} mm²/m "
        f"→ {bars_sec['description']}  (EC2 Cl 9.3.1.1(2))"
    )

    # Deflection
    rho   = max(sd["As_req"], section.As_min) / (1000.0 * d)
    rho_0 = math.sqrt(section.fck) / 1000.0
    defl = calculate_deflection_limit(
        fck=section.fck, fyk=section.fyk, rho=rho, rho_0=rho_0,
        is_end_span=section.is_end_span,
        support_condition=section.support_condition,
    )
    allow_ld = defl["value"]
    actual_ld = span / d
    defl_status = "OK" if actual_ld <= allow_ld else "FAIL"
    results["deflection_check"] = defl_status
    notes.append(
        f"Deflection: L/d = {actual_ld:.1f} vs allowable {allow_ld:.1f} → {defl_status}"
    )
    if defl_status == "FAIL":
        warnings.append(f"Deflection FAIL: L/d ({actual_ld:.1f}) > {allow_ld:.1f}. Increase h.")

    # Shear
    vrd_c_res = calculate_VRd_c(sd["bars"]["As_prov"], section.fck, 1000.0, d)
    VRd_c = vrd_c_res["value"]
    notes.append(vrd_c_res["note"])
    if V_Ed > VRd_c:
        results["shear_status"] = f"FAIL: V_Ed={V_Ed/1e3:.1f} kN > VRd,c={VRd_c/1e3:.1f} kN"
        warnings.append("Shear exceeds concrete capacity. Increase slab thickness.")
    else:
        results["shear_status"] = f"OK: V_Ed={V_Ed/1e3:.1f} kN ≤ VRd,c={VRd_c/1e3:.1f} kN"

    # Crack
    if sigma_s_qp is None:
        As_req_eff = max(sd["As_req"], section.As_min)
        sigma_s_qp = section.fyd * (As_req_eff / sd["bars"]["As_prov"])
    ck = crack_control_spacing(sigma_s_qp)
    results["crack_spacing_max_mm"] = ck["max_spacing_mm"]
    notes.append(ck["note"])

    return results


# ===========================================================================
# Two-way slab design
# ===========================================================================

def _design_two_way(section: EC2SlabSection, n: float, V_Ed: float,
                    sigma_s_qp: Optional[float], notes: list, warnings: list) -> dict:
    """Design a two-way slab. Returns partial results dict."""
    results = {}
    lx = section.lx
    ly = section.ly
    ly_lx = section.ly_lx

    # Coefficient lookup
    coeff = get_two_way_coefficients(section.panel_type, ly_lx)
    notes.append(coeff["note"])
    α_sx, α_sy, β_sx, β_sy = coeff["alpha_sx"], coeff["alpha_sy"], coeff["beta_sx"], coeff["beta_sy"]

    # Design moments per metre
    Msx  = α_sx * n * lx ** 2    # sagging short span
    Msy  = α_sy * n * lx ** 2    # sagging long span
    Mhx  = β_sx * n * lx ** 2    # hogging short span (at continuous support)
    Mhy  = β_sy * n * lx ** 2    # hogging long span

    notes.append(
        f"Moments (n={n*1e3:.3f} kN/m², lx={lx:.0f} mm):\n"
        f"  Sagging: m_sx={Msx/1e6:.2f} kN·m/m, m_sy={Msy/1e6:.2f} kN·m/m\n"
        f"  Hogging: m_hx={Mhx/1e6:.2f} kN·m/m, m_hy={Mhy/1e6:.2f} kN·m/m"
    )

    # Short-span sagging (outer layer, d_x)
    sx_sag = _design_strip(Msx, section.d_x, section, "Short sagging", section.As_min)
    notes.extend(sx_sag["notes"]); warnings.extend(sx_sag["warnings"])
    results["As_req_sx"]    = round(sx_sag["As_req"], 2)
    results["steel_sx_sag"] = sx_sag["bars"]["description"]

    # Long-span sagging (inner layer, d_y)
    sy_sag = _design_strip(Msy, section.d_y, section, "Long sagging", section.As_min)
    notes.extend(sy_sag["notes"]); warnings.extend(sy_sag["warnings"])
    results["As_req_sy"]    = round(sy_sag["As_req"], 2)
    results["steel_sy_sag"] = sy_sag["bars"]["description"]

    # Short-span hogging (at continuous edge)
    if Mhx > 0:
        sx_hog = _design_strip(Mhx, section.d_x, section, "Short hogging", section.As_min)
        notes.extend(sx_hog["notes"]); warnings.extend(sx_hog["warnings"])
        results["steel_sx_hog"] = sx_hog["bars"]["description"]

    # Long-span hogging
    if Mhy > 0:
        sy_hog = _design_strip(Mhy, section.d_y, section, "Long hogging", section.As_min)
        notes.extend(sy_hog["notes"]); warnings.extend(sy_hog["warnings"])
        results["steel_sy_hog"] = sy_hog["bars"]["description"]

    # Deflection — check short span
    rho_x  = max(sx_sag["As_req"], section.As_min) / (1000 * section.d_x)
    rho_0  = math.sqrt(section.fck) / 1000.0
    defl_x = calculate_deflection_limit(
        fck=section.fck, fyk=section.fyk, rho=rho_x, rho_0=rho_0,
        is_end_span=section.is_end_span,
        support_condition=section.support_condition,
    )
    act_ld = lx / section.d_x
    defl_status = "OK" if act_ld <= defl_x["value"] else "FAIL"
    results["deflection_check"] = defl_status
    notes.append(f"Deflection (short span): L/d={act_ld:.1f} vs {defl_x['value']:.1f} → {defl_status}")
    if defl_status == "FAIL":
        warnings.append(f"Deflection FAIL: L/d ({act_ld:.1f}) > {defl_x['value']:.1f}.")

    # Shear (critical support)
    vrd_c_res = calculate_VRd_c(sx_sag["bars"]["As_prov"], section.fck, 1000.0, section.d_x)
    VRd_c = vrd_c_res["value"]
    notes.append(vrd_c_res["note"])
    if V_Ed > VRd_c:
        results["shear_status"] = f"FAIL: V_Ed={V_Ed/1e3:.1f} kN > VRd,c={VRd_c/1e3:.1f} kN"
        warnings.append("Shear exceeds concrete capacity. Increase thickness.")
    else:
        results["shear_status"] = f"OK: V_Ed={V_Ed/1e3:.1f} kN ≤ VRd,c={VRd_c/1e3:.1f} kN"

    # Torsion reinforcement at corners of simply supported panels (EC2 Cl 9.3.2)
    if β_sx == 0.0 or β_sy == 0.0:
        As_tor = 0.75 * sx_sag["bars"]["As_prov"]
        notes.append(
            f"Corner torsion steel (EC2 Cl 9.3.2): provide As_tor = 0.75 × As_sx_sag "
            f"= {As_tor:.0f} mm²/m in both directions at simply supported corners, "
            "over lx/5 width and ly/5 depth."
        )
        results["corner_torsion_steel_mm2m"] = round(As_tor, 0)

    # Crack
    if sigma_s_qp is None:
        As_req_eff = max(sx_sag["As_req"], section.As_min)
        sigma_s_qp = section.fyd * (As_req_eff / sx_sag["bars"]["As_prov"])
    ck = crack_control_spacing(sigma_s_qp)
    results["crack_spacing_max_mm"] = ck["max_spacing_mm"]
    notes.append(ck["note"])

    return results


# ===========================================================================
# Public entry point
# ===========================================================================

def calculate_slab_reinforcement(
    section: EC2SlabSection,
    n: float,                       # Factored design load (N/mm²)
    V_Ed: float = 0.0,              # Design shear per metre at critical section (N/m)
    sigma_s_qp: Optional[float] = None,  # SLS steel stress for crack check
) -> dict:
    """
    Full EC2 solid slab design — one-way or two-way.

    Parameters
    ----------
    section     : ``EC2SlabSection``
    n           : Factored design load intensity (N/mm²) = 1.35Gk + 1.5Qk.
    V_Ed        : Design shear per unit width (N) at critical support section.
    sigma_s_qp  : Steel stress under quasi-permanent loads (N/mm²). Estimated
                  if not supplied.

    Returns
    -------
    dict with reinforcement descriptions, deflection/shear/crack status, notes, warnings.
    """
    notes: list[str] = []
    warnings: list[str] = []
    results: dict = {"status": "OK", "notes": notes, "warnings": warnings}

    notes.append(section.summary())
    notes.append(
        f"Design load: n = {n*1e3:.2f} kN/m²  (factored UDL)  "
        f"{'One-way' if section.slab_type == 'one-way' else 'Two-way'} slab"
    )

    if section.slab_type == "one-way":
        partial = _design_one_way(section, n, V_Ed, sigma_s_qp, notes, warnings)
    else:
        partial = _design_two_way(section, n, V_Ed, sigma_s_qp, notes, warnings)

    results.update(partial)

    if "FAIL" in results.get("deflection_check", ""):
        results["status"] = "Deflection Failure"
    if "FAIL" in results.get("shear_status", ""):
        if results["status"] == "OK":
            results["status"] = "Shear Failure"

    return results

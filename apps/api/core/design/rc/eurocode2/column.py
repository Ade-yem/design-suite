"""
BS EN 1992-1-1:2004 (EC2)  –  Column Design Orchestration
==========================================================
``calculate_column_reinforcement`` is the single entry point for RC column
design to EC2.

Imports
-------
  * ``EC2ColumnSection``  from ``models.ec2_column``              — section geometry
  * Formulas              from ``core.design.rc.eurocode2.formulas``
  * Bar selector          from ``core.design.rc.common.select_reinforcement``

Design sequence  (EC2 Cl 5.8 / 6.1)
--------------------------------------
1.  Section summary and design action logging.
2.  Minimum eccentricity — e₀ = max(h/30, 20 mm)  (Cl 6.1(4)).
3.  Slenderness classification in x and y  (Cl 5.8.3.1):
       λ ≤ λ_lim → short column (second-order effects negligible).
       λ > λ_lim → slender column (second-order moments must be added).
4.  Required As_min check with N_Ed  (Cl 9.5.2(2)):
       As_min = max(0.10 × N_Ed / fyd,  0.002 × Ac)
5.  Design moment including second-order effects for slender columns
    using the **Nominal Curvature** method  (Cl 5.8.8):
       M_02  — larger first-order end moment
       M_2   — second-order moment from e₂ = (1/r) × l₀²/10
       M_Ed  — governing design moment per Cl 5.8.8.2(3)
6.  Binary-search strain-compatibility to find minimum As satisfying
    the N_Ed, M_Ed interaction point.
7.  Bar selection (symmetric arrangement).
8.  Biaxial bending check if My > 0 or section is non-square  (Cl 5.8.9).
9.  Link (transverse reinforcement) detailing  (EC2 Cl 9.5.3):
       Minimum link diameter ≥ max(6 mm,  ¼ × main bar dia).
       Maximum link spacing ≤ min(20 × main bar dia, b, h, 400 mm).
       (UK NA: 400 mm limit.)
10. Shear capacity check  (EC2 Cl 6.2.2 — same formula as beams).

Modularity
----------
No formulae in this file. All physics lives in ``formulas.py``.
Section data lives in the model.
"""

from __future__ import annotations

import math
from typing import Optional

from models.ec2.column import EC2ColumnSection
from core.design.rc.common.select_reinforcement import select_column_reinforcement
from core.design.rc.eurocode2.formulas import (
    calculate_column_capacity,
    calculate_M2_nominal_curvature,
    check_biaxial_bending,
    column_min_eccentricity,
    calculate_VRd_c,
)


# ===========================================================================
# Main design function
# ===========================================================================

def calculate_column_reinforcement(
    section: EC2ColumnSection,
    N_Ed: float,            # Design axial force (N) — compression positive
    M_Edx: float,           # First-order design moment about x-axis (N·mm)
    M_Edy: float = 0.0,     # First-order design moment about y-axis (N·mm)
    M_01x: float = 0.0,     # Smaller first-order end moment about x (N·mm)
    M_01y: float = 0.0,     # Smaller first-order end moment about y
    V_Ed: float = 0.0,      # Coexisting shear force (N)
    phi_ef: float = 0.0,    # Effective creep ratio (0 → conservative A=0.7)
    K_phi: float = 1.0,     # Creep modification for curvature (Cl 5.8.8.3)
    r_m_x: float = 1.0,     # M_01/M_02 moment ratio about x
    r_m_y: float = 1.0,     # M_01/M_02 moment ratio about y
) -> dict:
    """
    Full EC2 column design.

    Parameters
    ----------
    section : ``EC2ColumnSection``
    N_Ed    : Design axial compressive force (N). Positive = compression.
    M_Edx   : Larger first-order moment about x-axis — h-direction (N·mm).
    M_Edy   : Larger first-order moment about y-axis — b-direction (N·mm).
    M_01x   : Smaller first-order moment about x (used for C factor in λ_lim).
    M_01y   : Smaller first-order moment about y.
    V_Ed    : Design shear force (N). If 0, shear check is skipped.
    phi_ef  : Effective creep ratio φ_ef (EC2 Cl 5.8.4). 0 uses A=0.7.
    K_phi   : Creep factor for curvature method (EC2 Eq. 5.37). Default 1.0.
    r_m_x   : Moment ratio M_01/M_02 about x for λ_lim (C factor).
    r_m_y   : Moment ratio M_01/M_02 about y.

    Returns
    -------
    dict with:
        status, slenderness_x, slenderness_y, lambda_lim_x, lambda_lim_y,
        M_Ed_design_x, M_Ed_design_y, M_2x, M_2y,
        As_req, As_prov, reinforcement_description,
        biaxial_check, shear_status, link_detail, notes, warnings.
    """
    notes: list[str] = []
    warnings: list[str] = []
    results: dict = {
        "status":          "OK",
        "slenderness_x":   "",
        "slenderness_y":   "",
        "lambda_lim_x":    0.0,
        "lambda_lim_y":    0.0,
        "M_Ed_design_x":   0.0,
        "M_Ed_design_y":   0.0,
        "M_2x":            0.0,
        "M_2y":            0.0,
        "As_req":          0.0,
        "As_prov":         0.0,
        "reinforcement_description": "None",
        "biaxial_check":   "Not required",
        "shear_status":    "Not checked",
        "link_detail":     "",
        "notes":           notes,
        "warnings":        warnings,
    }

    notes.append(section.summary())
    notes.append(
        f"Design actions: N_Ed = {N_Ed/1e3:.1f} kN, "
        f"M_Edx = {M_Edx/1e6:.2f} kN·m, M_Edy = {M_Edy/1e6:.2f} kN·m"
        + (f", V_Ed = {V_Ed/1e3:.1f} kN" if V_Ed > 0 else "")
    )

    h   = section.h
    b   = section.b
    fck = section.fck
    fyk = section.fyk
    fcd = section.fcd
    fyd = section.fyd
    d   = section.d
    d_prime = section.d_prime
    Ac  = section.Ac

    # =========================================================================
    # Step 1: Minimum eccentricity  (EC2 Cl 6.1(4))
    # =========================================================================
    e0_x = column_min_eccentricity(h, section.l_0x)
    e0_y = column_min_eccentricity(b, section.l_0y)
    notes.append(e0_x["note"])

    M_min_x = N_Ed * e0_x["e_0"]
    M_min_y = N_Ed * e0_y["e_0"]

    M_Edx_eff = max(abs(M_Edx), M_min_x)
    M_Edy_eff = max(abs(M_Edy), M_min_y)

    notes.append(
        f"Design moments after e₀: M_Edx = max({abs(M_Edx)/1e6:.2f}, {M_min_x/1e6:.2f}) = "
        f"{M_Edx_eff/1e6:.2f} kN·m;  M_Edy = {M_Edy_eff/1e6:.2f} kN·m"
    )

    # =========================================================================
    # Step 2: Slenderness and λ_lim  (EC2 Cl 5.8.3)
    # =========================================================================
    notes.append("--- Slenderness Check (EC2 Cl 5.8.3) ---")

    # Need a first-pass n for λ_lim (use As = As_min_geo conservatively)
    omega_est = (section.As_min_geo * fyd) / (Ac * fcd)
    n_est = N_Ed / (Ac * fcd)

    lambda_lim_x = section.lambda_lim(n_est, phi_ef, omega_est, r_m_x)
    lambda_lim_y = section.lambda_lim(n_est, phi_ef, omega_est, r_m_y)

    results["lambda_lim_x"] = round(lambda_lim_x, 1)
    results["lambda_lim_y"] = round(lambda_lim_y, 1)

    is_slender_x = section.lambda_x > lambda_lim_x
    is_slender_y = section.lambda_y > lambda_lim_y

    slender_str_x = "Slender" if is_slender_x else "Short"
    slender_str_y = "Slender" if is_slender_y else "Short"
    results["slenderness_x"] = slender_str_x
    results["slenderness_y"] = slender_str_y

    notes.append(
        f"x-axis (h={h}mm): λ_x = {section.lambda_x:.1f}, λ_lim = {lambda_lim_x:.1f} → {slender_str_x}\n"
        f"y-axis (b={b}mm): λ_y = {section.lambda_y:.1f}, λ_lim = {lambda_lim_y:.1f} → {slender_str_y}"
    )

    if section.lambda_x > 140 or section.lambda_y > 140:
        warnings.append(
            "Slenderness ratio > 140 — EC2 does not provide explicit rules beyond this. "
            "Consider increasing section size (Cl 5.8.1(3))."
        )

    # =========================================================================
    # Step 3: Required As_min from N_Ed  (EC2 Cl 9.5.2(2))
    # =========================================================================
    As_min_N = max(0.10 * N_Ed / fyd, section.As_min_geo)
    As_min   = As_min_N
    notes.append(
        f"As_min = max(0.10×N_Ed/fyd, 0.002Ac) = max({0.10*N_Ed/fyd:.0f}, {section.As_min_geo:.0f}) "
        f"= {As_min:.0f} mm²  (EC2 Cl 9.5.2(2))"
    )

    # =========================================================================
    # Step 4: Second-order moments for slender columns  (EC2 Cl 5.8.8)
    # =========================================================================
    M_2x = 0.0
    M_2y = 0.0

    if is_slender_x:
        notes.append("--- Second-order moment x-axis (EC2 Cl 5.8.8 Nominal Curvature) ---")
        # Use current As_min for curvature calculation (iterate if needed)
        m2_res_x = calculate_M2_nominal_curvature(
            N_Ed=N_Ed, fck=fck, fyk=fyk,
            b=b, h=h, d=d, l_0=section.l_0x,
            As_total=As_min, Ac=Ac, K_phi=K_phi,
        )
        M_2x = m2_res_x["M_2"]
        results["M_2x"] = round(M_2x / 1e6, 3)
        notes.append(m2_res_x["note"])

    if is_slender_y:
        notes.append("--- Second-order moment y-axis (EC2 Cl 5.8.8 Nominal Curvature) ---")
        m2_res_y = calculate_M2_nominal_curvature(
            N_Ed=N_Ed, fck=fck, fyk=fyk,
            b=h, h=b, d=section.d_prime,   # swap h↔b for y-axis
            l_0=section.l_0y,
            As_total=As_min, Ac=Ac, K_phi=K_phi,
        )
        M_2y = m2_res_y["M_2"]
        results["M_2y"] = round(M_2y / 1e6, 3)
        notes.append(m2_res_y["note"])

    # Total design moments: governing per Cl 5.8.8.2(3)
    # M_Ed = max(M_02 + M_2, M_0e + M_2, M_01 + 0.5·M_2)
    # Simplified (conservative): M_Ed = M_Edx_eff + M_2x
    M_design_x = M_Edx_eff + M_2x
    M_design_y = M_Edy_eff + M_2y

    results["M_Ed_design_x"] = round(M_design_x / 1e6, 3)
    results["M_Ed_design_y"] = round(M_design_y / 1e6, 3)

    notes.append(
        f"Total design moments (incl. 2nd order):\n"
        f"  M_Ed,x = {M_Edx_eff/1e6:.2f} + {M_2x/1e6:.2f} = {M_design_x/1e6:.2f} kN·m\n"
        f"  M_Ed,y = {M_Edy_eff/1e6:.2f} + {M_2y/1e6:.2f} = {M_design_y/1e6:.2f} kN·m"
    )

    # =========================================================================
    # Step 5: Binary-search strain-compatibility for minimum As  (EC2 Cl 6.1)
    # =========================================================================
    notes.append("--- Interaction Design — Strain Compatibility (EC2 Cl 6.1) ---")

    def check_As(Asc: float) -> tuple[bool, float]:
        """Return (passes, M_cap) for a trial Asc under N_Ed."""
        x_lo, x_hi = 1.0, 3.0 * h
        for _ in range(30):
            x_mid = (x_lo + x_hi) / 2.0
            N_cap, _ = calculate_column_capacity(
                x_mid, Asc, b, h, d, d_prime, fck, fyk, num_bars=8,
            )
            if N_cap < N_Ed:
                x_lo = x_mid
            else:
                x_hi = x_mid
        _, M_cap = calculate_column_capacity(
            x_hi, Asc, b, h, d, d_prime, fck, fyk, num_bars=8,
        )
        return M_cap >= M_design_x, M_cap

    # Binary search over As
    lo, hi = As_min, section.As_max
    best_As = None
    for _ in range(28):
        mid = (lo + hi) / 2.0
        ok, _ = check_As(mid)
        if ok:
            best_As = mid
            hi = mid
        else:
            lo = mid

    if best_As is None:
        ok, _ = check_As(section.As_max)
        if ok:
            best_As = section.As_max

    if best_As is None:
        results["status"] = "Section Inadequate"
        warnings.append(
            f"Section cannot carry N_Ed={N_Ed/1e3:.0f} kN + M_Ed={M_design_x/1e6:.2f} kN·m "
            f"even with As_max = {section.As_max:.0f} mm². Increase section."
        )
        return results

    results["As_req"] = round(best_As, 2)
    notes.append(f"Required reinforcement (interaction search): As_req = {best_As:.0f} mm²")

    # =========================================================================
    # Step 6: Bar selection and reinforcement detailing
    # =========================================================================
    bars = select_column_reinforcement(best_As, b, h)
    results["As_prov"]                   = bars["As_prov"]
    results["reinforcement_description"] = bars["description"]

    if bars["As_prov"] < As_min:
        warnings.append(
            f"As_prov ({bars['As_prov']:.0f}) < As_min ({As_min:.0f}) mm² (EC2 Cl 9.5.2(2))."
        )
        results["status"] = "Reinforcement Limit Failure"

    if bars["As_prov"] > section.As_max:
        warnings.append(
            f"As_prov ({bars['As_prov']:.0f}) > As_max ({section.As_max:.0f}) mm² (EC2 Cl 9.5.2(3))."
        )
        results["status"] = "Reinforcement Limit Failure"

    if bars["warning"]:
        warnings.append(bars["warning"])

    notes.append(
        f"Selected bars: {bars['description']}  (As_prov = {bars['As_prov']:.0f} mm²)"
    )

    # =========================================================================
    # Step 7: Biaxial bending check  (EC2 Cl 5.8.9)
    # =========================================================================
    needs_biaxial = M_Edy_eff > 0 or (b != h)

    if needs_biaxial:
        notes.append("--- Biaxial Bending Check (EC2 Cl 5.8.9) ---")

        # Moment capacities per axis at As_prov (find x for N_Ed)
        def axis_capacity(h_ax: float, b_ax: float, d_ax: float) -> float:
            x_lo, x_hi = 1.0, 3.0 * h_ax
            for _ in range(30):
                x_m = (x_lo + x_hi) / 2.0
                N_c, _ = calculate_column_capacity(
                    x_m, bars["As_prov"], b_ax, h_ax, d_ax, d_prime, fck, fyk,
                )
                if N_c < N_Ed:
                    x_lo = x_m
                else:
                    x_hi = x_m
            _, M_c = calculate_column_capacity(
                x_hi, bars["As_prov"], b_ax, h_ax, d_ax, d_prime, fck, fyk,
            )
            return M_c

        M_Rdx = axis_capacity(h, b, d)
        M_Rdy = axis_capacity(b, h, section.d)  # y-axis: swap b↔h

        # Axial capacity N_Rd
        N_Rd = fcd * Ac + bars["As_prov"] * fyd

        bx_res = check_biaxial_bending(
            M_Edx=M_design_x, M_Edy=M_design_y,
            M_Rdx=M_Rdx, M_Rdy=M_Rdy,
            N_Ed=N_Ed, N_Rd=N_Rd,
        )
        notes.append(bx_res["note"])
        results["biaxial_check"] = bx_res["status"]

        if bx_res["status"] == "FAIL":
            if results["status"] == "OK":
                results["status"] = "Biaxial Bending Failure"
            warnings.append(
                f"Biaxial interaction = {bx_res['interaction']:.3f} > 1.0. "
                "Increase section or reinforcement."
            )
    else:
        notes.append("Biaxial check not required (M_Edy = 0, square section or uniaxial).")

    # =========================================================================
    # Step 8: Link (transverse reinforcement) detailing  (EC2 Cl 9.5.3)
    # =========================================================================
    notes.append("--- Link Detailing (EC2 Cl 9.5.3) ---")
    bar_dia  = bars["dia"]
    min_link_dia = max(6.0, 0.25 * bar_dia)

    # Max spacing: min of 20 × ϕ_main, b, h, 400 mm  (UK NA to EC2 Cl 9.5.3(3))
    max_link_spacing = min(20.0 * bar_dia, b, h, 400.0)

    link_detail = (
        f"Links: Φ ≥ {min_link_dia:.0f} mm, spacing ≤ {max_link_spacing:.0f} mm  "
        f"(EC2 Cl 9.5.3)"
    )
    results["link_detail"] = link_detail
    notes.append(link_detail)

    if section.link_dia < min_link_dia:
        warnings.append(
            f"Link diameter ({section.link_dia} mm) < min required {min_link_dia:.0f} mm  "
            f"(EC2 Cl 9.5.3(1))."
        )

    # Every main bar (or alternate bar) must be restrained by a link
    # Corner bars always restrained; intermediate bars ≤ 150mm from restrained bar
    notes.append(
        "Every corner bar must be held by a link. Intermediate bars ≤ 150 mm "
        "from a restrained bar need not be held (EC2 Cl 9.5.3(6))."
    )

    # =========================================================================
    # Step 9: Shear check  (EC2 Cl 6.2.2)
    # =========================================================================
    if V_Ed > 0:
        notes.append("--- Shear Check (EC2 Cl 6.2.2) ---")
        vrd_res = calculate_VRd_c(bars["As_prov"], fck, b, d, N_Ed)
        VRd_c = vrd_res["value"]
        notes.append(vrd_res["note"])
        notes.append(f"V_Ed = {V_Ed/1e3:.1f} kN vs VRd,c = {VRd_c/1e3:.1f} kN")

        if V_Ed <= VRd_c:
            results["shear_status"] = f"OK: V_Ed ({V_Ed/1e3:.1f}) ≤ VRd,c ({VRd_c/1e3:.1f}) kN"
        else:
            results["shear_status"] = (
                f"FAIL: V_Ed ({V_Ed/1e3:.1f}) > VRd,c ({VRd_c/1e3:.1f}) kN — shear links required."
            )
            if results["status"] == "OK":
                results["status"] = "Shear Failure"
            warnings.append(
                f"Shear: V_Ed ({V_Ed/1e3:.1f} kN) > VRd,c ({VRd_c/1e3:.1f} kN). "
                "Design shear reinforcement per EC2 Cl 6.2.3."
            )

    return results

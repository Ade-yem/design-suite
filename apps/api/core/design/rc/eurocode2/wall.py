"""
BS EN 1992-1-1:2004 (EC2)  –  Reinforced Concrete Wall Design  (Clause 9.6)
=============================================================================
``design_reinforced_wall`` is the single entry point for RC wall design per EC2.

Design sequence
---------------
1.  **Slenderness classification** (Cl 5.8.3)
      λ = l₀ / i, where i = h / √12 for rectangular walls.
      λ_lim = 20·A·B·C / √n (using recommended simplified A=0.7, B=1.1, C=0.7).
      If λ > λ_lim, the wall is slender and requires second-order moment checks.

2.  **Eccentricity check & Initial moment** (Cl 6.1(4))
      Minimum eccentricity e₀ = max(h/30, 20 mm).
      M_0Ed = max(M_applied, N_Ed × e₀).

3.  **Additional moment for slender walls** (Cl 5.8.8)
      If slender, second-order moment M₂ is calculated via Nominal Curvature.
      M_Ed = M_0Ed + M₂.

4.  **Axial and Flexural resistance** (Cl 6.1)
      For this simplified routine, the required vertical steel is the envelope
      (maximum) of the pure axial demand and pure flexural demand.
      (Rigorous interaction curve methods are recommended for edge cases).

5.  **Vertical reinforcement selection** (Cl 9.6.2)
      As_vmin = 0.002·Ac  ;  As_vmax = 0.04·Ac.
      Spacing limits min(3h, 400 mm).

6.  **Horizontal reinforcement** (Cl 9.6.3)
      As_hmin = max(0.25 × As_vprov, 0.001·Ac).
      Spacing limits 400 mm.

7.  **In-plane shear check** (Cl 6.2.2)
      If horizontal shear V_h is provided, VRd,c is checked.
"""

from __future__ import annotations

import math
from typing import Optional

from models.ec2.wall import EC2WallSection
from core.design.rc.eurocode2.formulas import (
    calculate_k,
    calculate_lever_arm,
    calculate_singly_reinforced,
    calculate_M2_nominal_curvature,
    calculate_VRd_c,
    column_min_eccentricity,
)
from core.design.rc.common.select_reinforcement import select_slab_reinforcement

def design_reinforced_wall(
    section: EC2WallSection,
    n_v: float,                        # Factored axial load intensity (N/mm per unit length)
    M: float = 0.0,                    # Factored bending moment per unit length (N·mm/m)
    V_h: Optional[float] = None,       # In-plane horizontal shear per unit length (N/mm)
) -> dict:
    """
    Design a 1 m strip of a reinforced concrete wall per EC2.

    Parameters
    ----------
    section : ``EC2WallSection`` — geometry and material model.
    n_v     : Factored ultimate axial load intensity (N/mm). 
    M       : Factored design bending moment per unit length (N·mm/m).
    V_h     : In-plane horizontal shear intensity per unit length (N/mm). Optional.

    Returns
    -------
    dict: Complete wall design output including required steel and calculation notes.
    """
    notes: list[str] = []
    warnings: list[str] = []
    results: dict = {"status": "OK", "notes": notes, "warnings": warnings}

    notes.append(section.summary())
    notes.append(
        f"Design actions: n_v = {n_v:.2f} N/mm  ({n_v:.0f} kN/m), "
        f"M_applied = {M/1e6:.2f} kN·m/m"
    )

    h   = section.h
    fck = section.fck
    fyk = section.fyk
    d   = section.d
    fcd = section.fcd
    b   = 1000.0    # 1 m strip
    Ac  = b * h     # mm² per meter

    # 1. Slenderness & Initial Eccentricity
    i_radius = h / math.sqrt(12.0)
    lam = section.l_0 / i_radius
    
    n_relative = n_v * 1000.0 / (Ac * fcd)   # n = NEd / (Ac fcd)
    n_relative = max(n_relative, 0.01)       # avoid division by zero
    
    # Recommended default limits: A=0.7, B=1.1, C=0.7 => A*B*C = 0.539
    # Limit: λ_lim = 20 * 0.539 / √n = 10.78 / √n
    lam_lim = 10.78 / math.sqrt(n_relative)
    is_slender = lam > lam_lim
    
    slender_str = "Slender" if is_slender else "Stocky"
    results["slenderness"] = slender_str
    notes.append(
        f"Slenderness: λ = l₀/i = {section.l_0:.0f}/{i_radius:.1f} = {lam:.1f}. "
        f"Limit λ_lim = 10.78/√n = {lam_lim:.1f}. Wall is {slender_str}."
    )

    ecc_res = column_min_eccentricity(h, section.l_0)
    e_0 = ecc_res["e_0"]
    notes.append(ecc_res["note"])

    M_min = n_v * e_0   # initial moment based on min eccentricity (N.mm / m)
    M_0Ed = max(abs(M), M_min)
    notes.append(f"M_0Ed = max(M_applied, N_Ed × e₀) = max({M/1e6:.2f}, {M_min/1e6:.2f}) = {M_0Ed/1e6:.2f} kN·m/m")
    
    M_Ed = M_0Ed
    
    # 2. Second order moment M2 via Nominal Curvature
    if is_slender:
        # Approximate As_total for M2 calculation - use user minimum as starting point
        As_approx = section.As_min_v
        m2_res = calculate_M2_nominal_curvature(
            N_Ed=n_v * 1000.0, fck=fck, fyk=fyk, b=b, h=h, d=d, l_0=section.l_0,
            As_total=As_approx, Ac=Ac
        )
        M_2 = m2_res["M_2"] / 1000.0  # normalized back to N.mm/m
        notes.append(m2_res["note"])
        M_Ed += M_2
        notes.append(f"Slender wall second-order moment M₂ = {M_2/1e6:.2f} kN·m/m. Total M_Ed = {M_Ed/1e6:.2f} kN·m/m.")

    results["M_Ed_kNm_m"] = round(M_Ed / 1e6, 2)

    # 3. Axial & Flexural requirements envelope (Simplified approach)
    notes.append("--- Axial & Flexural Capacity (Simplified Envelope Method) ---")
    
    # Pure Axial required steel
    N_Rd_c = fcd * Ac / 1000.0   # force per mm length
    results["n_capacity_concrete_kNm"] = round(N_Rd_c, 2)
    notes.append(f"Concrete axial capacity: N_Rd,c = fcd × Ac = {N_Rd_c:.2f} kN/m")
    
    As_req_v_axial = 0.0
    if n_v > N_Rd_c:
        As_req_v_axial = (n_v - N_Rd_c) * 1000.0 / section.fyd
        notes.append(f"Axial steel required: Asc = (n_v - N_Rd,c) / fyd = {As_req_v_axial:.1f} mm²/m")
    else:
        notes.append("Concrete carries full axial load. Axial steel required = 0 mm²/m")

    # Flexural required steel
    k_res = calculate_k(M_Ed, fck, b, d)
    K = k_res["value"]
    notes.append(k_res["note"])

    K_lim = 0.167
    As_req_v_flex = 0.0
    if K > K_lim:
        warnings.append(f"Moment factor K ({K:.4f}) > K_lim (0.167). Section is inadequate for the design moment (compression steel required).")
        results["status"] = "Section Inadequate (moment)" 
    else:
        z_res = calculate_lever_arm(d, K)
        notes.append(z_res["note"])
        As_req_v_flex = calculate_singly_reinforced(M_Ed, fyk, z_res["value"])["value"]
        notes.append(f"Flexural steel required: As = {As_req_v_flex:.1f} mm²/m")

    As_req_v = max(As_req_v_axial, As_req_v_flex, section.As_min_v)
    if As_req_v > section.As_max_v:
        warnings.append(f"Required vertical steel {As_req_v:.1f} mm²/m exceeds maximum limit {section.As_max_v:.1f} mm²/m.")
        results["status"] = "Reinforcement Limit Failure"
        
    results["As_req_v"] = round(As_req_v, 2)
    notes.append(f"Governing required vertical steel As_req_v = {As_req_v:.1f} mm²/m")

    # 4. Vertical Bar Selection
    notes.append("--- Vertical Steel Selection ---")
    bars_v = select_slab_reinforcement(As_req_v, d, h, fyk)
    results["As_prov_v"] = bars_v["As_prov"]
    results["vertical_steel"] = bars_v["description"]
    
    if bars_v["warning"]: warnings.append(bars_v["warning"])
    notes.append(f"Vertical steel: {bars_v['description']} (As_prov = {bars_v['As_prov']:.1f} mm²/m)")

    s_v_max = min(3.0 * h, 400.0)
    if bars_v["spacing"] > s_v_max:
         warnings.append(f"Vertical bar spacing ({bars_v['spacing']} mm) > limit {s_v_max:.0f} mm (Cl 9.6.2(3)).")

    # 5. Horizontal Steel
    notes.append("--- Horizontal Steel (Cl 9.6.3) ---")
    As_h_req = max(section.As_min_h, 0.25 * bars_v["As_prov"])
    bars_h = select_slab_reinforcement(As_h_req, d, h, fyk)  # uses same selection logic as slabs
    results["As_req_h"] = round(As_h_req, 2)
    results["horizontal_steel"] = bars_h["description"]
    
    if bars_h["warning"]: warnings.append(bars_h["warning"])
    notes.append(f"Horizontal steel: As_req_h = {As_h_req:.1f} mm²/m → {bars_h['description']}")
    
    if bars_h["spacing"] > 400.0:
        warnings.append(f"Horizontal bar spacing ({bars_h['spacing']} mm) > limit 400 mm (Cl 9.6.3(2)).")

    # 6. In-plane Horizontal Shear
    if V_h is not None:
        notes.append("--- In-plane Shear Check (Cl 6.2.2) ---")
        VRd_c_res = calculate_VRd_c(bars_h["As_prov"], fck, 1000.0, d, N_Ed=n_v*1000.0)
        VRd_c = VRd_c_res["value"]
        notes.append(VRd_c_res["note"])
        
        # total V_b per meter
        V_Ed_h = V_h * 1000.0  # N per meter
        
        if V_Ed_h > VRd_c:
            results["shear_status"] = f"FAIL: V_Ed_h ({V_Ed_h/1e3:.1f} kN/m) > VRd,c ({VRd_c/1e3:.1f} kN/m)"
            warnings.append("In-plane shear exceeds concrete capacity. Shear reinforcement required or increase wall section.")
            if results["status"] == "OK":
                results["status"] = "Shear Failure"
        else:
            results["shear_status"] = f"OK: V_Ed_h ({V_Ed_h/1e3:.1f} kN/m) ≤ VRd,c ({VRd_c/1e3:.1f} kN/m)"

    return results

"""
BS EN 1992-1-1:2004 (EC2)  –  Staircase Design
==============================================
``calculate_staircase_reinforcement`` is the main entry point.
"""

from typing import Optional
import math

from models.ec2.staircase import EC2StaircaseSection
from core.design.rc.common.select_reinforcement import select_slab_reinforcement
from core.design.rc.eurocode2.formulas import (
    calculate_k,
    calculate_lever_arm,
    calculate_singly_reinforced,
    calculate_VRd_c,
    calculate_deflection_limit,
    crack_control_spacing,
)

# Material constants
UNIT_WEIGHT_CONCRETE = 25.0  # kN/m³

def _self_weight_waist(waist_mm: float, cos_alpha: float) -> float:
    """Self-weight of inclined waist slab projected onto plan (kN/m²)."""
    waist_m = waist_mm / 1000.0
    return UNIT_WEIGHT_CONCRETE * waist_m / (cos_alpha ** 2)

def _self_weight_steps(riser_mm: float) -> float:
    """Self-weight of triangular steps projected onto plan (kN/m²)."""
    riser_m = riser_mm / 1000.0
    return UNIT_WEIGHT_CONCRETE * riser_m / 2.0

def calculate_staircase_reinforcement(
    section: EC2StaircaseSection,
    imposed_load: float,
    finishes_load: float = 1.5,
    gamma_G: float = 1.35,
    gamma_Q: float = 1.50,
    M_hogging_support: Optional[float] = None,
    sigma_s_qp: Optional[float] = None,
) -> dict:
    """
    Full staircase flexural and serviceability design per Eurocode 2.

    Parameters
    ----------
    section          : EC2StaircaseSection geometry / material object
    imposed_load     : Characteristic live load q_k (kN/m²)
    finishes_load    : Characteristic superimposed dead load g_k,fin (kN/m²). Default 1.5.
    gamma_G          : ULS partial factor for permanent load. Default 1.35.
    gamma_Q          : ULS partial factor for variable load. Default 1.50.
    M_hogging_support: Design hogging moment at interior support (N·mm/m) for continuous flights.
    sigma_s_qp       : Steel stress under quasi-permanent loads (N/mm²) for crack check.

    Returns
    -------
    dict
        A dictionary containing reinforcement details, applied loads, structural calculations, and design status notes.
    """
    notes: list[str] = []
    warnings: list[str] = []
    results: dict = {"status": "OK", "notes": notes, "warnings": warnings}

    notes.append(section.summary())

    # Step 1: Effective span
    l_eff = section.span
    results["effective_span_mm"] = l_eff
    notes.append(f"Effective span (on plan) = {l_eff:.0f} mm = {l_eff/1000:.3f} m")

    # Step 2: Loading
    angle_deg = math.degrees(section.angle)
    cos_alpha = section.cos_alpha
    gk_waist = _self_weight_waist(section.waist, cos_alpha)
    gk_steps = _self_weight_steps(section.riser)
    gk_total = gk_waist + gk_steps + finishes_load

    n_design = gamma_G * gk_total + gamma_Q * imposed_load

    results["loading"] = {
        "gk_waist_kNm2":    round(gk_waist, 3),
        "gk_steps_kNm2":    round(gk_steps, 3),
        "gk_finishes_kNm2": round(finishes_load, 3),
        "gk_total_kNm2":    round(gk_total, 3),
        "qk_kNm2":          round(imposed_load, 3),
        "n_design_kNm2":    round(n_design, 3),
    }

    notes.append(
        f"Characteristic loads (on plan):\n"
        f"  g_k,waist   = {gk_waist:.2f} kN/m²\n"
        f"  g_k,steps   = {gk_steps:.2f} kN/m²\n"
        f"  g_k,fin     = {finishes_load:.2f} kN/m²\n"
        f"  g_k,total   = {gk_total:.2f} kN/m²\n"
        f"  q_k         = {imposed_load:.2f} kN/m²\n"
        f"  n_design    = {gamma_G}×{gk_total:.2f} + {gamma_Q}×{imposed_load:.2f} = {n_design:.2f} kN/m²"
    )

    w_per_m = n_design * 1.0  # kN/m
    w_Nmm = w_per_m          # N/mm

    # Step 3: Moments
    if section.support_condition == "simple":
        M_sag = w_Nmm * (l_eff ** 2) / 8.0
        M_hog = 0.0
        notes.append(f"Simply supported: M_sag = wl²/8 = {M_sag/1e6:.2f} kN·m/m")
    else:
        M_sag = 0.086 * w_Nmm * (l_eff ** 2)
        M_hog = M_hogging_support if M_hogging_support is not None else 0.086 * w_Nmm * (l_eff ** 2)
        notes.append(
            f"Continuous stair: M_sag = {M_sag/1e6:.2f} kN·m/m  |  "
            f"M_hog = {M_hog/1e6:.2f} kN·m/m"
        )

    M_design = max(M_sag, M_hog)
    results["design_moments_kNm_per_m"] = {
        "M_sagging": round(M_sag / 1e6, 2),
        "M_hogging": round(M_hog / 1e6, 2),
        "M_governing": round(M_design / 1e6, 2),
    }

    # Step 4: Flexure
    b = 1000.0
    d = section.d
    K_lim = 0.167 if section.delta >= 1.0 else max(0.60 * section.delta - 0.18 * section.delta ** 2 - 0.21, 0.0)
    
    k_res = calculate_k(M_design, section.fck, b, d)
    K = k_res["value"]
    notes.append(k_res["note"])

    if K > K_lim:
        warnings.append(f"K ({K:.4f}) > K_lim ({K_lim:.3f}). Increase waist thickness.")
        results["status"] = "Section Inadequate"
        As_req = None
    else:
        z_res = calculate_lever_arm(d, K, section.delta)
        notes.append(z_res["note"])
        As_req_val = calculate_singly_reinforced(M_design, section.fyk, z_res["value"])["value"]
        As_design = max(As_req_val, section.As_min)
        notes.append(f"As_req = {As_req_val:.1f} mm²/m  (min={section.As_min:.1f} mm²/m → {As_design:.1f} mm²/m)")
        As_req = As_req_val

    results["As_req"] = round(As_req, 2) if As_req is not None else None

    # Step 5: Reinforcement selection
    if As_req is not None:
        As_needed = max(As_req, section.As_min)
        bars = select_slab_reinforcement(As_needed, d, section.waist, section.fyk)
        results["As_prov"] = bars["As_prov"]
        results["main_steel"] = bars["description"]
        if bars["warning"]:
            warnings.append(bars["warning"])
        notes.append(f"Main steel: {bars['description']} (As={bars['As_prov']:.1f} mm²/m)")

        if bars["As_prov"] > section.As_max:
            warnings.append(f"Reinforcement > As_max ({section.As_max:.1f} mm²/m)")
            results["status"] = "Reinforcement Limit Failure"
    else:
        bars = None

    # Step 6: Secondary / Distribution steel
    if bars is not None:
        As_sec_min = max(0.20 * bars["As_prov"], section.As_min * 0.20)
        sec_bars = select_slab_reinforcement(As_sec_min, section.d_dist, section.waist, section.fyk)
        results["secondary_steel"] = sec_bars["description"]
        results["secondary_As_prov"] = sec_bars["As_prov"]
        notes.append(
            f"Distribution steel: ≥ 20% of main = {As_sec_min:.0f} mm²/m "
            f"→ {sec_bars['description']}"
        )

    # Step 7: Deflection
    if bars is not None and As_req is not None:
        rho = max(As_req, section.As_min) / (1000.0 * d)
        rho_0 = math.sqrt(section.fck) / 1000.0
        defl = calculate_deflection_limit(
            fck=section.fck, fyk=section.fyk, rho=rho, rho_0=rho_0,
            is_end_span=section.is_end_span,
            support_condition=section.support_condition,
        )
        allow_ld = defl["value"]
        
        # Adjust for stairs: Cl 7.4.2 says same as slabs
        actual_ld = l_eff / d
        defl_status = "OK" if actual_ld <= allow_ld else "FAIL"
        results["deflection_check"] = defl_status
        notes.append(f"Deflection L/d: actual {actual_ld:.1f} vs allowable {allow_ld:.1f} → {defl_status}")
        if defl_status == "FAIL":
            results["status"] = "Deflection Failure"
            warnings.append(f"Deflection FAIL: Actual L/d ({actual_ld:.1f}) > {allow_ld:.1f}.")

    # Step 8: Shear
    if section.support_condition == "simple":
        V_Ed = w_Nmm * l_eff / 2.0
    else:
        V_Ed = 0.6 * w_Nmm * l_eff

    results["design_shear_kN_per_m"] = round(V_Ed / 1e3, 2)
    
    if bars is not None:
        vrd_c_res = calculate_VRd_c(bars["As_prov"], section.fck, 1000.0, d)
        VRd_c = vrd_c_res["value"]
        notes.append(vrd_c_res["note"])
        
        if V_Ed > VRd_c:
            results["shear_status"] = f"FAIL: V_Ed={V_Ed/1e3:.1f} kN > VRd,c={VRd_c/1e3:.1f} kN"
            warnings.append("Shear exceeds concrete capacity. Increase waist thickness.")
            if results["status"] == "OK":
                results["status"] = "Shear Failure"
        else:
            results["shear_status"] = f"OK: V_Ed={V_Ed/1e3:.1f} kN ≤ VRd,c={VRd_c/1e3:.1f} kN"

    # Step 9: Cracking limits
    if bars is not None:
        if sigma_s_qp is None:
            As_req_eff = max(As_req, section.As_min)
            fyd = section.fyk / 1.15
            sigma_s_qp = fyd * (As_req_eff / bars["As_prov"])
        
        ck = crack_control_spacing(sigma_s_qp)
        results["crack_spacing_max_mm"] = ck["max_spacing_mm"]
        notes.append(ck["note"])

    return results

def calculate_landing_reinforcement(
    thickness: float,
    span: float,
    n: float,
    cover: float = 25.0,
    fck: float = 30.0,
    fyk: float = 500.0,
    support_condition: str = "continuous",
    delta: float = 1.0,
) -> dict:
    """
    Design a landing slab for EC2 connected to the staircase.

    Parameters
    ----------
    thickness        : Landing slab depth (mm).
    span             : Effective span of the landing (mm).
    n                : Factored design UDL (N/mm²).
    cover            : Nominal concrete cover (mm). Default is 25.0.
    fck              : Characteristic concrete cylinder strength (N/mm²). Default is 30.0.
    fyk              : Characteristic steel yield strength (N/mm²). Default is 500.0.
    support_condition: Boundary condition ("simple" or "continuous"). Default is "continuous".
    delta            : Moment redistribution factor (0.7-1.0). Default is 1.0.

    Returns
    -------
    dict
        A dictionary containing reinforcement details, deflection, shear, and crack control status.
    """
    from models.ec2.slab import EC2SlabSection
    from core.design.rc.eurocode2.slab import calculate_slab_reinforcement

    landing_slab = EC2SlabSection(
        h=thickness,
        cover=cover,
        fck=fck,
        lx=span,
        ly=span,
        fyk=fyk,
        slab_type="one-way",
        support_condition=support_condition,
        delta=delta,
    )

    V_Ed = n * span / 2.0 if support_condition == "simple" else 0.6 * n * span
    return calculate_slab_reinforcement(landing_slab, n, V_Ed)

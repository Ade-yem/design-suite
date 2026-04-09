"""
BS 8110-1:1997  –  Staircase Design  (Clause 3.10)
===================================================
``calculate_staircase_reinforcement`` is the single entry point.
It accepts a ``StaircaseSection`` model and design loading, then executes
the full code-prescribed design sequence:

1.  Effective span determination     (Cl 3.10.1.2 / 3.10.1.3)
2.  Load combination                 (Cl 3.10.1.2)
    – Dead: self-weight of waist + steps + finishes, all projected on plan
    – Live: imposed load on plan area
3.  Flexural design                  (Cl 3.10.1 referencing Cl 3.4.4)
    – K / K' / lever arm / As,req
4.  Bar selection                    (Cl 3.12.11.2 spacing limits)
5.  Distribution steel               (Cl 3.12.5.3 / 3.5.2.3)
6.  Deflection check                 (Cl 3.10.2.2 / 3.4.6)
7.  Shear check                      (Cl 3.10.2.2 / 3.4.5)
8.  Detailing notes                  (Cl 3.10.3 – landing reinforcement)

Load projection convention (Cl 3.10.1.2):
    Loads on inclined slabs are expressed per unit *plan* area, not slope.
    The self-weight component of such an inclined slab is:
        w_sw = γ_c × mean_thickness / cos(α) × (1/cos(α))
    which simplifies to γ_c × mean_thickness / cos²(α) per plan area.
    However, BS 8110 Cl 3.10.1.2 states loads on stairs where the flight
    occupies at least 60% of the span may be treated as uniform on plan area.
"""

from typing import Optional
import math

from models.bs8110.staircase import StaircaseSection
from services.design.rc.common.select_reinforcement import select_slab_reinforcement
from services.design.rc.bs8110.formulas import (
    calculate_k,
    calculate_k_prime,
    calculate_lever_arm,
    calculate_singly_reinforced_section,
    check_shear_stress,
    calculate_vc,
    check_deflection,
    check_reinforcement_limits,
    determine_basic_ratio,
)

# ---------------------------------------------------------------------------
# Material constants
# ---------------------------------------------------------------------------
GAMMA_C_CONC = 25e-3   # kN/mm² → N/mm² ×10⁻³ → use 25 kN/m³ = 25×10⁻⁶ N/mm³
UNIT_WEIGHT_CONCRETE = 25.0  # kN/m³

# ===========================================================================
# Helpers
# ===========================================================================

def _self_weight_waist(waist_mm: float, cos_alpha: float) -> float:
    """
    Self-weight of inclined waist slab projected onto plan (kN/m²).

    w_sw = γ_c × (waist / cos α) × (1/cos α) [slope area → plan area]
         = γ_c × waist / cos²(α)

    But BS 8110 Cl 3.10.1.2 allows using plan projection for flights
    occupying ≥ 60% of span, so:
        w_sw = γ_c × mean_thickness (on plan)
    Here we use the conservative inclined formula.

    Parameters
    ----------
    waist_mm  : Waist thickness (mm)
    cos_alpha : cosine of inclination angle
    """
    waist_m = waist_mm / 1000.0
    return UNIT_WEIGHT_CONCRETE * waist_m / (cos_alpha ** 2)


def _self_weight_steps(riser_mm: float) -> float:
    """
    Self-weight of triangular steps projected onto plan (kN/m²).

    Half the step triangle: w_steps = γ_c × riser/2
    (plan dimension of tread cancels)
    """
    riser_m = riser_mm / 1000.0
    return UNIT_WEIGHT_CONCRETE * riser_m / 2.0


# ===========================================================================
# Main design entry point
# ===========================================================================

def calculate_staircase_reinforcement(
    section: StaircaseSection,
    imposed_load: float,           # Characteristic imposed (live) load q_k (kN/m²)
    finishes_load: float = 1.5,    # Superimposed dead load (finishes) g_k,fin (kN/m²)
    gamma_G: float = 1.4,          # Partial safety factor for dead load
    gamma_Q: float = 1.6,          # Partial safety factor for imposed load
    M_hogging_support: Optional[float] = None,  # Applied hogging moment (N·mm/m) if continuous
    av: Optional[float] = None,    # Distance from support to first load (mm) for shear enhancement
) -> dict:
    """
    Full staircase flexural and serviceability design per BS 8110-1:1997 Cl 3.10.

    Parameters
    ----------
    section          : StaircaseSection geometry / material object
    imposed_load     : Characteristic live load q_k (kN/m²)
    finishes_load    : Characteristic superimposed dead load g_k,fin (kN/m²). Default 1.5.
    gamma_G          : ULS partial factor for dead load.   Default 1.4.
    gamma_Q          : ULS partial factor for imposed load. Default 1.6.
    M_hogging_support: Design hogging moment at interior support (N·mm/m) for continuous flights.
                       If None, the flight is treated as simply supported for sagging design.
    av               : Distance to first point load from support face (mm) for shear enhancement.
    """
    notes: list[str] = []
    warnings: list[str] = []
    results: dict = {"status": "OK", "notes": notes, "warnings": warnings}

    notes.append(section.summary())

    # =========================================================================
    # Step 1: Effective Span  (BS 8110 Cl 3.10.1.3)
    # =========================================================================
    # BS 8110 Cl 3.10.1.3: effective span = lesser of:
    #   (a) Distance between centrelines of supports
    #   (b) Clear span + effective depth (for simply supported)
    #
    # The section.span is taken as the already-adjusted effective span on plan.
    # We report it and record the assumption.
    l_eff = section.span  # mm — on plan
    results["effective_span_mm"] = l_eff
    notes.append(
        f"Effective span (on plan) = {l_eff:.0f} mm = {l_eff/1000:.3f} m  "
        f"(BS 8110 Cl 3.10.1.3 — user-provided; confirm = min of c/c or clear+d)"
    )

    # =========================================================================
    # Step 2: Loading  (BS 8110 Cl 3.10.1.2)
    # =========================================================================
    angle_deg = math.degrees(section.angle)
    cos_alpha = section.cos_alpha

    notes.append(f"Flight inclination α = {angle_deg:.1f}° (R={section.riser}mm, T={section.tread}mm)")

    # ---- Characteristic dead loads ----
    # 2a. Waist self-weight on plan
    gk_waist = _self_weight_waist(section.waist, cos_alpha)

    # 2b. Step self-weight on plan
    gk_steps = _self_weight_steps(section.riser)

    # 2c. Total characteristic dead load per m² plan
    gk_total = gk_waist + gk_steps + finishes_load

    # ---- Design UDL on plan ----
    n_design = gamma_G * gk_total + gamma_Q * imposed_load   # kN/m²

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
        f"  g_k,waist   = {gk_waist:.2f} kN/m²  [25 × {section.waist/1000:.3f}/cos²α]\n"
        f"  g_k,steps   = {gk_steps:.2f} kN/m²  [25 × R/2]\n"
        f"  g_k,fin     = {finishes_load:.2f} kN/m² (user-provided)\n"
        f"  g_k,total   = {gk_total:.2f} kN/m²\n"
        f"  q_k         = {imposed_load:.2f} kN/m²\n"
        f"  n_design    = {gamma_G}×{gk_total:.2f} + {gamma_Q}×{imposed_load:.2f} = {n_design:.2f} kN/m²"
    )

    # Convert to N/mm (per metre width = per 1000 mm) for formulas
    # n [kN/m²] × 1 [kN/kN] × 1000/1000 [m/mm] = n × 1e-3 [N/mm²]
    n_Nmm2 = n_design * 1e-3   # N/mm²

    # =========================================================================
    # Step 3: Design Moments  (simply supported or continuous)
    # =========================================================================
    # For 1m wide strip: w (N/mm per metre width) = n [N/mm²] × 1000 [mm/m] = n_Nmm2 × 1000
    w_per_m = n_Nmm2 * 1000.0  # N/mm (linear load on 1m strip)

    if section.support_condition == "simple":
        # M_sag = wl²/8
        M_sag = w_per_m * l_eff ** 2 / 8.0   # N·mm/m
        M_hog = 0.0
        notes.append(
            f"Simply supported: M_sag = wl²/8 = {w_per_m:.3f}×{l_eff}²/8 = {M_sag/1e6:.2f} kN·m/m"
        )
    else:
        # Continuous: use Table 3.12-style coefficients (landing–flight–landing).
        # BS 8110 Cl 3.10.1.3 references Cl 3.5.2 for continuous one-way slabs.
        # For preliminary design: M_sag ≈ 0.086 wl², M_hog ≈ 0.086 wl²
        M_sag = 0.086 * w_per_m * l_eff ** 2
        M_hog = M_hogging_support if M_hogging_support is not None else 0.086 * w_per_m * l_eff ** 2
        notes.append(
            f"Continuous stair: M_sag = 0.086wl² = {M_sag/1e6:.2f} kN·m/m  |  "
            f"M_hog (support) = {M_hog/1e6:.2f} kN·m/m"
        )
        notes.append(
            "Note: Coefficients from BS 8110 Table 3.12 via Cl 3.10.1.3. Verify continuity prerequisites (Cl 3.5.2.1)."
        )

    M_design = max(M_sag, M_hog)   # Governs bar requirement
    results["design_moments_kNm_per_m"] = {
        "M_sagging":  round(M_sag / 1e6, 2),
        "M_hogging":  round(M_hog / 1e6, 2),
        "M_governing": round(M_design / 1e6, 2),
    }

    # =========================================================================
    # Step 4: Flexural Design  (Cl 3.10.1 / Cl 3.4.4)
    # =========================================================================
    notes.append("--- Flexural Design (BS 8110 Cl 3.4.4) ---")
    b = 1000.0   # 1m strip
    d = section.d
    fcu = section.fcu
    fy = section.fy

    k_prime_res = calculate_k_prime(section.beta_b)
    K_prime = k_prime_res["value"]
    notes.append(k_prime_res["note"])

    k_res = calculate_k(M_design, fcu, b, d)
    K = k_res["value"]
    notes.append(k_res["note"])

    if K > K_prime:
        warnings.append(
            f"K ({K:.4f}) > K' ({K_prime:.4f}): Waist is too thin — increase thickness. "
            "Compression reinforcement in staircases is impractical."
        )
        results["status"] = "Section Inadequate"
        As_req = None
    else:
        z_res = calculate_lever_arm(d, K)
        notes.append(z_res["note"])
        As_req_val = calculate_singly_reinforced_section(M_design, fy, z_res["value"])["value"]
        As_design = max(As_req_val, section.As_min)
        notes.append(f"As_req = {As_req_val:.1f} mm²/m  (min={section.As_min:.1f} mm²/m  →  using {As_design:.1f} mm²/m)")
        As_req = As_req_val

    results["As_req"] = round(As_req, 2) if As_req is not None else None

    # =========================================================================
    # Step 5: Bar Selection  (Cl 3.12.11.2 spacing / crack control)
    # =========================================================================
    if As_req is not None:
        As_needed = max(As_req, section.As_min)
        bars = select_slab_reinforcement(As_needed, d, section.waist, fy, section.beta_b)
        results["As_prov"]                   = bars["As_prov"]
        results["reinforcement_description"] = bars["description"]
        if bars["warning"]:
            warnings.append(bars["warning"])
        notes.append(f"Main steel: {bars['description']}  (As_prov = {bars['As_prov']:.1f} mm²/m)")

        # Step 5b: Reinforcement limits
        lim_res = check_reinforcement_limits(bars["As_prov"], section.As_min, section.As_max, "tension")
        notes.append(lim_res["note"])
        if lim_res["status"] == "FAIL":
            results["status"] = "Reinforcement Limit Failure"
    else:
        bars = None

    # =========================================================================
    # Step 6: Distribution Steel  (Cl 3.12.5.3 / Cl 3.5.2.3)
    # =========================================================================
    # Minimum 20% of main steel area or As_min, placed perpendicular to flight
    if bars is not None:
        As_dist_req = max(0.20 * bars["As_prov"], section.As_min)
        dist_bars = select_slab_reinforcement(
            As_dist_req, section.d_dist, section.waist, fy, 1.0
        )
        results["distribution_steel"]       = dist_bars["description"]
        results["distribution_As_prov"]     = dist_bars["As_prov"]
        notes.append(
            f"Distribution steel (Cl 3.5.2.3): As_dist = max(0.2×As_prov, As_min) = "
            f"{As_dist_req:.0f} mm²/m → {dist_bars['description']}"
        )

    # =========================================================================
    # Step 7: Deflection Check  (BS 8110 Cl 3.10.2.2 / Cl 3.4.6)
    # =========================================================================
    notes.append("--- Deflection Check (BS 8110 Cl 3.10.2.2 / 3.4.6) ---")
    # Cl 3.10.2.2: for staircases, the deflection limit is span/250 for visual
    # acceptability, but the code uses the same span/d ratio method as for slabs.
    # Table 3.9: simple=20, continuous=26 (rectangular section)
    basic_ratio = determine_basic_ratio("rectangular", section.support_condition)
    # Cl 3.10.2.2 bonus: if stair occupies ≥ 60% of the span, the basic ratio
    # for deflection may be increased by 15%.
    flight_fraction = (section.num_steps * section.tread) / l_eff
    ratio_factor = 1.15 if flight_fraction >= 0.60 else 1.0
    adj_basic_ratio = basic_ratio * ratio_factor
    if ratio_factor > 1.0:
        notes.append(
            f"Cl 3.10.2.2 bonus: flight occupies {flight_fraction*100:.0f}% of span (≥60%) "
            f"→ basic L/d ratio increased by 15%: {basic_ratio} × 1.15 = {adj_basic_ratio:.1f}"
        )

    if bars is not None and As_req is not None:
        def_res = check_deflection(
            l_eff, d, adj_basic_ratio,
            bars["As_prov"], As_req,
            b, M_sag, fy, 0.0, section.beta_b,
        )
        results["deflection_check"] = def_res["status"]
        notes.append(def_res["note"])
        if def_res["status"] == "FAIL":
            results["status"] = "Deflection Failure"
            warnings.append(
                f"Deflection FAIL: Actual L/d={def_res['actual']:.1f} > Allowable={def_res['allowable']:.1f}. "
                "Increase waist thickness."
            )

    # =========================================================================
    # Step 8: Shear Check  (BS 8110 Cl 3.10.2.2 / Cl 3.4.5)
    # =========================================================================
    notes.append("--- Shear Check (BS 8110 Cl 3.10.2.2 / 3.4.5) ---")
    # Design shear at face of support: V = w × l/2 for SS, 0.6wl for first interior
    if section.support_condition == "simple":
        V_design = w_per_m * l_eff / 2.0   # N/m strip
    else:
        V_design = 0.6 * w_per_m * l_eff   # N/m strip  (Table 3.12 coeff)

    results["design_shear_kN_per_m"] = round(V_design / 1e3, 2)
    shear_res = check_shear_stress(V_design, b, d, fcu)
    notes.append(shear_res["note"])

    if shear_res["status"] == "FAIL":
        results["status"] = "Shear Failure (v > v_max)"
    elif bars is not None:
        vc_res = calculate_vc(bars["As_prov"], b, d, fcu, section.waist)
        vc = vc_res["value"]
        notes.append(vc_res["note"])

        if shear_res["v"] <= vc:
            results["shear_status"] = "OK — No shear links required"
            notes.append("v ≤ vc: No shear reinforcement required.")
        else:
            results["shear_status"] = f"FAIL: v ({shear_res['v']:.3f}) > vc ({vc:.3f})"
            if results["status"] == "OK":
                results["status"] = "Shear Failure"
            warnings.append(
                f"Shear stress {shear_res['v']:.3f} N/mm² > vc {vc:.3f} N/mm². "
                "Increase waist thickness — shear links in stairs are impractical."
            )

    # =========================================================================
    # Step 9: Detailing Notes  (BS 8110 Cl 3.10.3 / 3.12)
    # =========================================================================
    notes.append("--- Detailing Requirements ---")

    # Landing reinforcement: the stair bars should extend into the landing ≥ anchorage length
    # BS 8110 Cl 3.10.3 references Cl 3.12.8 for bond lengths
    anchorage_dia = bars["dia"] if bars else int(section.bar_dia)
    bond_length_factor = 40  # conservative: 40Φ for high-yield tension (Cl 3.12.8.4)
    anchorage_mm = bond_length_factor * anchorage_dia
    results["anchorage_into_landing_mm"] = anchorage_mm
    notes.append(
        f"Anchorage into landing (Cl 3.10.3 / 3.12.8): bars extend ≥ {bond_length_factor}Φ = "
        f"{anchorage_mm} mm into each landing."
    )

    # Top steel over supports (continuous case)
    if section.support_condition == "continuous":
        notes.append(
            "Continuous flight: Provide top steel over landings = As_prov of sagging steel, "
            "extending ≥ 0.25 × span from the support centreline into both spans."
        )

    # No links needed (slab-type): BS 8110 Cl 3.5.2.2 — no shear links if v < vc
    notes.append(
        "Shear links: Not normally required for slab-type staircase flights (Cl 3.5.2.2). "
        "If shear failure found, increase waist rather than adding links."
    )

    # Step nose reinforcement note
    notes.append(
        "Step nosing: Consider U-bars or bent main bars at each step nosing to resist "
        "localised cracking at stress concentration points."
    )

    # Lateral distribution at bottom of flight
    notes.append(
        "Lateral restraint: Ensure the lower landing provides adequate lateral restraint "
        "to the stair flight. Model the landing as a rigid diaphragm for analysis."
    )

    return results


# ===========================================================================
# Convenience: Landing Design  (Cl 3.10.1.3)
# ===========================================================================

def calculate_landing_reinforcement(
    thickness: float,   # Landing slab thickness (mm)
    span: float,        # Effective span of landing (mm)
    n: float,           # Design UDL (N/mm²) — same as stair or higher for landing UDL
    cover: float = 25.0,
    fcu: float = 30.0,
    fy: float = 500.0,
    support_condition: str = "continuous",
    beta_b: float = 1.0,
) -> dict:
    """
    Design a landing slab connected to the staircase flight.

    BS 8110 Cl 3.10.1.3: The landing may be designed as a one-way slab
    using the appropriate moment coefficients from Table 3.12.

    Parameters
    ----------
    thickness   : Landing slab depth (mm)
    span        : Effective span of landing (mm)
    n           : Design UDL in N/mm²
    """
    from models.slab import SlabSection

    notes = []
    warnings = []
    results = {"status": "OK", "notes": notes, "warnings": warnings}

    # Build a 1m-strip SlabSection to mirror the slab design logic
    landing_slab = SlabSection(
        h=thickness,
        cover=cover,
        fcu=fcu,
        lx=span,
        ly=span,   # One-way — ly = lx
        fy=fy,
        slab_type="one-way",
        support_condition=support_condition,
        beta_b=beta_b,
    )

    # Total load on landing = n × span (per metre width)
    F = n * span   # N/m — total design load per metre width

    from services.design.rc.bs8110.slab import design_one_way_slab
    landing_results = design_one_way_slab(landing_slab, F)

    notes.append(f"Landing slab design (Cl 3.10.1.3 via Cl 3.5.2):")
    notes.extend(landing_results.get("notes", []))
    warnings.extend(landing_results.get("warnings", []))
    results.update(landing_results)

    return results

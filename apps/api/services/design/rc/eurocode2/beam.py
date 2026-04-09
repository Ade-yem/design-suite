"""
BS EN 1992-1-1:2004 (EC2)  –  Beam Design Orchestration
=========================================================
``calculate_beam_reinforcement`` is the single entry point.

It imports:
  * ``EC2BeamSection``     from ``models.ec2_beam``          — section geometry / materials
  * Calculation functions  from ``services.design.rc.eurocode2.formulas`` — EC2 formulae
  * Bar-selection helpers  from ``services.design.rc.common.select_reinforcement``

Design sequence  (mirrors the structure of the BS 8110 beam service)
----------------------------------------------------------------------
1.  Section summary and action logging.
2.  Effective flange width check for T/L beams (EC2 Cl 5.3.2.1).
3.  Hogging/sagging classification (flange in compression only for sagging).
4.  Iterative flexural design loop (adjusts d if two bar layers required):
      a. Compute K = M/(b·d²·fck).
      b. Compare K with K_lim (from δ per Cl 5.5).
      c. Singly reinforced → z → As  (Cl 6.1).
      d. Doubly reinforced → As, As'  (K > K_lim).
      e. Flanged (NA in flange or web) → two-part T/L approach.
5.  Bar selection and layer check.
6.  Compression-steel selection (if required).
7.  Side reinforcement check for deep beams (EC2 Cl 9.2.4).
8.  Reinforcement limits — As_min (Cl 9.2.1.1) and As_max (Cl 9.2.1.1(3)).
9.  Deflection check via span/d ratio (EC2 Cl 7.4.2 Eq. 7.16a/b).
10. Shear — VRd,c check (EC2 Cl 6.2.2 Eq. 6.2).
11. Shear link design via Variable Strut Inclination (EC2 Cl 6.2.3).
12. Crack-width control — bar spacing via Table 7.3N (EC2 Cl 7.3.3).
13. Curtailment shift rule note (EC2 Cl 9.2.1.3).

Modularity
----------
This file is purely orchestration — it contains no mathematical formulae.
All physics lives in ``formulas.py``; all section data lives in the model.
"""

from __future__ import annotations

import math
from typing import Optional

from models.ec2.beam import EC2BeamSection
from services.design.rc.common.select_reinforcement import select_beam_reinforcement
from services.design.rc.eurocode2.formulas import (
    calculate_k,
    calculate_lever_arm,
    calculate_singly_reinforced,
    calculate_doubly_reinforced,
    calculate_flanged_beam,
    calculate_VRd_c,
    calculate_shear_links,
    calculate_deflection_limit,
    crack_control_spacing,
    curtailment_shift,
)


# ===========================================================================
# Helpers — encapsulate minor support checks so orchestration stays readable
# ===========================================================================

def _effective_flange_width_ec2(
    b_w: float,
    b_total: float,
    l_0: float,
    flange_type: str = "T",
) -> float:
    """
    Effective flange width per EC2 Cl 5.3.2.1.

    b_eff = b_w + Σ b_eff,i
    b_eff,i = min(0.2·b_i + 0.1·l_0,  0.2·l_0,  b_i)   per side

    Parameters
    ----------
    b_w         : Web width (mm)
    b_total     : Full slab width each side of web: (b_total − b_w)/2 per side.
                  For an L-beam, this is the one-sided slab width.
    l_0         : Distance between points of zero moment ≈ 0.7 × span for continuous
                  or 1.0 × span for simply supported.
    flange_type : ``"T"`` (symmetric) or ``"L"`` (one side only).
    """
    b_per_side = (b_total - b_w) / 2.0 if flange_type == "T" else (b_total - b_w)
    b_eff_side = min(0.2 * b_per_side + 0.1 * l_0, 0.2 * l_0, b_per_side)
    b_eff_side = max(b_eff_side, 0.0)

    n_sides = 2 if flange_type == "T" else 1
    return b_w + n_sides * b_eff_side


def _side_reinf_check(h: float, b: float, fyk: float) -> dict:
    """
    EC2 Cl 9.2.4: longitudinal skin reinforcement required in beams
    where h > 1000 mm (or h > 750 mm for UK practice — conservative).

    Returns a dict with 'required' bool, 'As_req', 'note'.
    """
    threshold = 1000.0   # EC2 Cl 9.2.4 — UK NA accepts 750 mm
    if h <= threshold:
        return {
            "required": False,
            "note": f"h = {h} mm ≤ {threshold} mm — no side reinforcement required (Cl 9.2.4).",
        }
    # Minimum 0.001 × b × (h − 600)/2 mm² each face (conservative interpretation)
    side_h = (h - 600.0) / 2.0
    As_side = max(0.001 * b * side_h, 0.0)
    return {
        "required": True,
        "As_req": round(As_side, 0),
        "note": (
            f"h = {h} mm > {threshold} mm — side reinforcement required (EC2 Cl 9.2.4). "
            f"As_skin ≥ {As_side:.0f} mm² each face in the middle zone."
        ),
    }


# ===========================================================================
# Main design function
# ===========================================================================

def calculate_beam_reinforcement(
    section: EC2BeamSection,
    M: float,               # Design moment (N·mm); negative = hogging
    V: float,               # Design shear (N); always positive magnitude
    span: float,            # Effective span (mm)
    N_Ed: float = 0.0,      # Axial force (N); positive = compression
    theta_deg: float = 21.8,# Initial strut angle for VSI shear design (°)
    sigma_s_qp: Optional[float] = None,  # Steel stress under quasi-permanent loads
                                          # for crack control; if None, estimated.
) -> dict:
    """
    Complete EC2 beam design orchestration.

    Parameters
    ----------
    section      : ``EC2BeamSection`` — all geometry and material properties.
    M            : Design moment at section (N·mm). Positive = sagging,
                   negative = hogging.
    V            : Design shear force (N). Magnitude (always positive).
    span         : Effective span (mm) — used for deflection check.
    N_Ed         : Coexisting axial force (N). Positive = compression.
                   Influences VRd,c. Default 0.
    theta_deg    : Initial strut angle for Variable Strut Inclination shear
                   design (EC2 Cl 6.2.3). Default 21.8° (cot θ = 2.5).
    sigma_s_qp   : Steel stress under quasi-permanent SLS loads (N/mm²).
                   Used for crack control spacing check (EC2 Table 7.3N).
                   If not provided, estimated as 0.6 × fyd.

    Returns
    -------
    dict with keys:
        status, As_req, As_prov, reinforcement_description,
        As_prime_req, As_prime_prov, compression_reinforcement_description,
        shear_links_Asw_s, shear_links_description,
        deflection_check, crack_control_spacing_mm, curtailment_shift_mm,
        notes, warnings.
    """
    notes: list[str] = []
    warnings: list[str] = []

    results: dict = {
        "status":                               "OK",
        "As_req":                               0.0,
        "As_prov":                              0.0,
        "reinforcement_description":            "None",
        "As_prime_req":                         0.0,
        "As_prime_prov":                        0.0,
        "compression_reinforcement_description":"None",
        "shear_links_Asw_s":                   None,
        "shear_links_description":              "Minimum links",
        "deflection_check":                     "Not checked",
        "crack_control_spacing_mm":             None,
        "curtailment_shift_mm":                 None,
        "notes":                                notes,
        "warnings":                             warnings,
    }

    # =========================================================================
    # Step 0: Summary and notation
    # =========================================================================
    is_hogging = M < 0
    M_Ed = abs(M)

    notes.append(section.summary())
    notes.append(
        f"Design actions: M_Ed = {M_Ed/1e6:.2f} kN·m "
        f"({'Hogging' if is_hogging else 'Sagging'}), "
        f"V_Ed = {V/1e3:.2f} kN, span = {span:.0f} mm"
        + (f", N_Ed = {N_Ed/1e3:.1f} kN (compression)" if N_Ed > 0 else "")
    )

    b   = section.b
    h   = section.h
    fck = section.fck
    fyk = section.fyk
    fywk = section.fywk
    d_prime = section.d_prime

    # =========================================================================
    # Step 1: Effective flange width  (EC2 Cl 5.3.2.1)
    # =========================================================================
    eff_b = b   # default: web width only (rectangular, or hogging flanged)
    flange_type = "T"   # default; could be "L" — take T conservatively

    if section.section_type == "flanged" and not is_hogging:
        # Sagging: flange in compression — use effective flange width
        l_0 = 0.85 * span if section.support_condition == "continuous" else span
        eff_b_code = _effective_flange_width_ec2(b, section.bf, l_0, flange_type)
        if section.bf > eff_b_code:
            warnings.append(
                f"Provided bf ({section.bf} mm) exceeds EC2 Cl 5.3.2.1 limit "
                f"({eff_b_code:.0f} mm) for l_0 = {l_0:.0f} mm. Using code limit."
            )
            eff_b = eff_b_code
        else:
            eff_b = section.bf
        notes.append(
            f"Effective flange width: b_eff = {eff_b:.0f} mm  "
            f"(EC2 Cl 5.3.2.1, l_0 = {l_0:.0f} mm)"
        )
    elif section.section_type == "flanged" and is_hogging:
        notes.append(
            "Hogging moment: flange in tension — using rectangular section (b = web width)."
        )

    # =========================================================================
    # Step 2: Iterative flexural design (adjusts d if 2 bar layers required)
    # =========================================================================
    current_d = section.d
    As_req     = 0.0
    As_prime_req = 0.0
    final_bars  = None

    for iteration in range(1, 4):
        notes.append(f"--- Flexural design iteration {iteration} (d = {current_d:.1f} mm) ---")

        # ---- Compute K ----
        k_res = calculate_k(M_Ed, fck, eff_b, current_d)
        K = k_res["value"]
        notes.append(k_res["note"])

        K_lim = section.K_lim

        # ---- Route to correct design method ----
        if section.section_type == "flanged" and not is_hogging:
            # T/L beam — flanged design handles NA-in-flange vs NA-in-web
            fl_res = calculate_flanged_beam(
                M=M_Ed, fck=fck, fyk=fyk,
                bw=b, bf=eff_b, d=current_d, hf=section.hf,
                d_prime=d_prime, delta=section.delta,
            )
            As_req      = fl_res["As_req"]
            As_prime_req = fl_res["As_prime"]
            notes.append(fl_res["note"])

        elif K > K_lim:
            # Doubly reinforced (rectangular or hogging flanged treated as rect.)
            notes.append(
                f"K ({K:.4f}) > K_lim ({K_lim:.3f}) — compression steel required."
            )
            dr_res = calculate_doubly_reinforced(
                M=M_Ed, fck=fck, fyk=fyk,
                b=eff_b, d=current_d, d_prime=d_prime, delta=section.delta,
            )
            As_req       = dr_res["As"]
            As_prime_req = dr_res["As_prime"]
            notes.append(dr_res["note"])

        else:
            # Singly reinforced
            z_res = calculate_lever_arm(current_d, K, section.delta)
            notes.append(z_res["note"])
            sr_res = calculate_singly_reinforced(M_Ed, fyk, z_res["value"])
            As_req = sr_res["value"]
            notes.append(sr_res["note"])

        # ---- Bar selection for this iteration ----
        As_design = max(As_req, section.As_min)
        tens_bars = select_beam_reinforcement(
            As_req=As_design,
            b_available=b,
            cover=section.cover,
            link_dia=section.link_dia,
        )
        final_bars = tens_bars

        # ---- Converge d for 2-layer arrangements ----
        if tens_bars["layers"] > 1:
            gap   = 25.0
            new_d = h - section.cover - section.link_dia - tens_bars["dia"] - gap / 2.0
            if abs(new_d - current_d) < 1.0:
                notes.append(f"d converged at {new_d:.1f} mm (two-layer arrangement).")
                break
            current_d = new_d
            notes.append(f"Two layers required — recalculating with d = {current_d:.1f} mm.")
        else:
            break

    # Store primary flexural results
    results["As_req"]                    = round(As_req, 2)
    results["As_prov"]                   = final_bars["As_prov"]
    results["reinforcement_description"] = final_bars["description"]
    if final_bars["warning"]:
        warnings.append(final_bars["warning"])
    notes.append(
        f"Main tension steel: {final_bars['description']}  "
        f"(As_prov = {final_bars['As_prov']:.1f} mm²)"
    )

    # =========================================================================
    # Step 3: Compression steel  (if doubly reinforced)
    # =========================================================================
    results["As_prime_req"] = round(As_prime_req, 2)
    if As_prime_req > 0:
        comp_bars = select_beam_reinforcement(
            As_req=As_prime_req,
            b_available=b,
            cover=section.cover,
            link_dia=section.link_dia,
        )
        results["As_prime_prov"] = comp_bars["As_prov"]
        results["compression_reinforcement_description"] = comp_bars["description"]
        notes.append(
            f"Compression steel (doubly-reinforced): {comp_bars['description']}  "
            f"(As' = {comp_bars['As_prov']:.1f} mm²)"
        )

    # =========================================================================
    # Step 4: Side (skin) reinforcement  (EC2 Cl 9.2.4)
    # =========================================================================
    side_res = _side_reinf_check(h, b, fyk)
    notes.append(side_res["note"])
    if side_res["required"]:
        warnings.append(
            f"Side reinforcement: provide ≥ {side_res['As_req']:.0f} mm² each face "
            "in the middle depth zone (EC2 Cl 9.2.4)."
        )

    # =========================================================================
    # Step 5: Reinforcement limits  (EC2 Cl 9.2.1.1)
    # =========================================================================
    notes.append("--- Reinforcement Limits (EC2 Cl 9.2.1.1) ---")
    As_prov = final_bars["As_prov"]

    if As_prov < section.As_min:
        results["status"] = "Reinforcement Limit Failure (As < As_min)"
        warnings.append(
            f"As_prov ({As_prov:.1f}) < As_min ({section.As_min:.1f}) mm²  (EC2 Cl 9.2.1.1)."
        )
    if As_prov > section.As_max:
        results["status"] = "Reinforcement Limit Failure (As > As_max)"
        warnings.append(
            f"As_prov ({As_prov:.1f}) > As_max ({section.As_max:.1f}) mm²  (EC2 Cl 9.2.1.1(3))."
        )
    notes.append(
        f"As_min = {section.As_min:.1f} mm², As_max = {section.As_max:.1f} mm²  |  "
        f"As_prov = {As_prov:.1f} mm² → "
        + ("OK" if section.As_min <= As_prov <= section.As_max else "FAIL")
    )

    # =========================================================================
    # Step 6: Deflection — L/d ratio  (EC2 Cl 7.4.2)
    # =========================================================================
    notes.append("--- Deflection Check (EC2 Cl 7.4.2) ---")
    rho     = As_req / (b * current_d)
    rho_0   = math.sqrt(fck) / 1000.0
    rho_prime = (results["As_prime_prov"] / (b * current_d)
                 if results["As_prime_prov"] > 0 else 0.0)

    b_t_bw = eff_b / b if section.section_type == "flanged" and not is_hogging else 1.0
    is_end  = section.support_condition == "continuous"

    defl_res = calculate_deflection_limit(
        fck=fck, fyk=fyk, rho=rho, rho_0=rho_0,
        is_end_span=is_end,
        support_condition=section.support_condition,
        rho_prime=rho_prime,
        b_t_bw=b_t_bw,
    )

    # Steel-stress modification: allowable_L/d × (As_req/As_prov)
    # i.e. multiply by (As_req/As_prov) if over-provisioned (conservative simplification)
    prov_factor = min(As_prov / max(As_req, section.As_min), 1.5)   # cap at 1.5
    allowable_ld = defl_res["value"] * prov_factor

    actual_ld = span / current_d
    defl_status = "OK" if actual_ld <= allowable_ld else "FAIL"
    results["deflection_check"] = defl_status

    notes.append(
        defl_res["note"] + f"\n"
        f"  Steel stress modification factor = {prov_factor:.2f}\n"
        f"  Allowable L/d = {defl_res['value']:.1f} × {prov_factor:.2f} = {allowable_ld:.1f}\n"
        f"  Actual    L/d = span/d = {span:.0f}/{current_d:.0f} = {actual_ld:.1f} → {defl_status}"
    )
    if defl_status == "FAIL":
        if results["status"] == "OK":
            results["status"] = "Deflection Failure"
        warnings.append(
            f"Deflection FAIL: actual L/d ({actual_ld:.1f}) > allowable ({allowable_ld:.1f}). "
            "Increase depth, add compression steel, or reduce span."
        )

    # =========================================================================
    # Step 7: Shear — VRd,c check  (EC2 Cl 6.2.2)
    # =========================================================================
    notes.append("--- Shear Design (EC2 Cl 6.2) ---")
    vrd_c_res = calculate_VRd_c(
        As_prov=As_prov,
        fck=fck,
        b_w=b,
        d=current_d,
        N_Ed=N_Ed,
    )
    VRd_c = vrd_c_res["value"]
    notes.append(vrd_c_res["note"])

    notes.append(
        f"V_Ed = {V/1e3:.1f} kN  vs  VRd,c = {VRd_c/1e3:.1f} kN"
    )

    if V <= VRd_c:
        # Minimum links only  (Cl 9.2.2 — all beams must have links)
        rho_w_min = 0.08 * math.sqrt(fck) / fywk
        Asw_s_min = rho_w_min * b   # mm²/mm
        results["shear_links_Asw_s"]       = round(Asw_s_min, 4)
        results["shear_links_description"] = "Minimum links only"
        notes.append(
            f"V_Ed ≤ VRd,c — concrete shear capacity sufficient. "
            f"Minimum links required (Cl 9.2.2): Asw/s ≥ {Asw_s_min:.4f} mm²/mm  "
            f"(ρw,min = {rho_w_min:.4f})"
        )
    else:
        # =========================================================================
        # Step 8: Shear link design — Variable Strut Inclination (EC2 Cl 6.2.3)
        # =========================================================================
        notes.append("--- Shear Link Design — VSI Method (EC2 Cl 6.2.3) ---")
        lnk_res = calculate_shear_links(
            V_Ed=V,
            fck=fck,
            fywk=fywk,
            b_w=b,
            d=current_d,
            theta_deg=theta_deg,
            z=0.9 * current_d,
        )
        notes.append(lnk_res["note"])

        if lnk_res["status"] != "OK":
            results["status"] = lnk_res["status"]
            warnings.append(lnk_res["status"])
        else:
            Asw_s = lnk_res["Asw_s"]
            results["shear_links_Asw_s"]       = Asw_s
            results["shear_links_description"] = (
                f"Asw/s = {Asw_s:.4f} mm²/mm  (θ = {lnk_res['theta_deg']}°, "
                f"cot θ = {lnk_res['cot_theta']})"
            )

    # =========================================================================
    # Step 9: Crack control — bar spacing  (EC2 Cl 7.3.3 Table 7.3N)
    # =========================================================================
    notes.append("--- Crack Control (EC2 Cl 7.3.3 / Table 7.3N) ---")
    # Estimate quasi-permanent steel stress if not provided:
    # σ_s ≈ fyd × (As_req / As_prov)  (SLS fraction of fyd)
    if sigma_s_qp is None:
        sigma_s_qp = (fyk / 1.15) * (max(As_req, section.As_min) / As_prov)

    ck_res = crack_control_spacing(sigma_s_qp)
    results["crack_control_spacing_mm"] = ck_res["max_spacing_mm"]
    notes.append(ck_res["note"])

    # Check actual bar spacing
    if final_bars["dia"] > 0 and final_bars["num"] > 1:
        # Estimated actual spacing edge-to-edge:
        side_cover = section.cover + section.link_dia
        inner_width = b - 2.0 * side_cover - final_bars["num"] * final_bars["dia"]
        actual_spacing = inner_width / (final_bars["num"] - 1) + final_bars["dia"]
        notes.append(f"Estimated bar c/c spacing ≈ {actual_spacing:.0f} mm.")
        if actual_spacing > ck_res["max_spacing_mm"]:
            warnings.append(
                f"Bar spacing ({actual_spacing:.0f} mm) > crack limit ({ck_res['max_spacing_mm']} mm) "
                f"for σ_s = {sigma_s_qp:.0f} N/mm². Use closer or smaller bars."
            )

    # =========================================================================
    # Step 10: Curtailment shift note  (EC2 Cl 9.2.1.3)
    # =========================================================================
    cot_theta = lnk_res["cot_theta"] if (
        isinstance(results["shear_links_Asw_s"], float) and
        results["shear_links_description"] != "Minimum links only"
    ) else 2.5

    cs_res = curtailment_shift(current_d, cot_theta)
    results["curtailment_shift_mm"] = cs_res["value"]
    notes.append(cs_res["note"])

    return results

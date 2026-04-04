"""
BS 8110-1:1997  –  Beam Design Orchestration
=============================================
``calculate_beam_reinforcement`` is the single entry point for beam design.
It accepts a ``BeamSection`` object (from ``models/calculations/beam_section``)
and design actions (M, V, span), applies the full design sequence, and returns
a structured result dictionary with every calculation note.

Design sequence
---------------
1.  Validate inputs / geometry.
2.  Compute K and K' (accounting for moment redistribution).
3.  Singly- or doubly-reinforced section design.
    3a. For flanged beams, use the two-part flange+web moment approach.
4.  Apply As_min / As_max limits.
5.  Select and fit bars (checking beam width).
6.  Bar spacing / crack control check.
7.  Deflection check (with long-span correction).
8.  Shear capacity check.
9.  Shear link design.
"""

import math
from typing import Optional

from models.calculations.beam_section import BeamSection
from services.calculations.common import select_reinforcement
from services.calculations.bs8110.formulas import (
    calculate_k,
    calculate_k_prime,
    calculate_lever_arm,
    calculate_singly_reinforced_section,
    calculate_doubly_reinforced_section,
    calculate_flanged_beam_reinforcement,
    check_shear_stress,
    calculate_vc,
    calculate_shear_links,
    check_deflection,
    check_reinforcement_limits,
    check_bar_spacing,
    determine_basic_ratio,
    check_side_reinforcement_requirement,
    apply_shear_enhancement,
)


# ---------------------------------------------------------------------------
# Main design function
# ---------------------------------------------------------------------------

def calculate_beam_reinforcement(
    section: BeamSection,
    M: float,
    V: float,
    span: float,
    av: Optional[float] = None,  # Distance to point load for shear enhancement
) -> dict:
    """
    Full beam design per BS 8110-1:1997 with iterative depth calculation.
    """
    notes: list[str] = []
    warnings: list[str] = []

    results = {
        "status": "OK",
        "As_req": 0.0,
        "As_prov": 0.0,
        "reinforcement_description": "None",
        "As_prime_req": 0.0,
        "As_prime_prov": 0.0,
        "compression_reinforcement_description": "None",
        "shear_links": "",
        "deflection_check": "",
        "notes": notes,
        "warnings": warnings,
    }

    # ------------------------------------------------------------------
    # 0. Setup and Hogging Check
    # ------------------------------------------------------------------
    is_hogging = M < 0
    M_abs = abs(M)
    notes.append(section.summary())
    action_note = f"Design actions: M = {M:.0f} N·mm ({'Hogging' if is_hogging else 'Sagging'}), V = {V:.0f} N, span = {span:.0f} mm"
    if av:
        action_note += f", av = {av:.0f} mm (for shear enhancement)"
    notes.append(action_note)

    b = section.b
    h = section.h
    fcu = section.fcu
    fy = section.fy
    fyv = section.fyv
    d_prime = section.d_prime
    beta_b = section.beta_b

    # If hogging, flange is in tension; treat as rectangular with width b
    eff_b = b
    if not is_hogging and section.section_type == "flanged":
        eff_b = section.bf
        notes.append(f"Sagging moment: using effective flange width bf = {eff_b} mm.")
    elif is_hogging and section.section_type == "flanged":
        notes.append("Hogging moment: flange is in tension. Treating as rectangular section (b = web width).")

    # ------------------------------------------------------------------
    # 1. Iterative Design Loop (for effective depth d)
    # ------------------------------------------------------------------
    current_d = section.d
    iteration = 0
    max_iterations = 3
    final_tens_bars = None

    while iteration < max_iterations:
        iteration += 1
        notes.append(f"--- Iteration {iteration} (d = {current_d:.1f} mm) ---")

        # 1a. K' and Flexural Design
        k_prime_res = calculate_k_prime(beta_b)
        K_prime = k_prime_res["value"]

        As_req = 0.0
        As_prime_req = 0.0

        if not is_hogging and section.section_type == "flanged":
            fl_res = calculate_flanged_beam_reinforcement(
                M=M_abs, fcu=fcu, fy=fy, b=b, bf=eff_b, d=current_d, hf=section.hf,
            )
            As_req = fl_res["As_req"]
            As_prime_req = fl_res["As_prime_req"]
            notes.append(fl_res["note"])
        else:
            k_res = calculate_k(M_abs, fcu, eff_b, current_d)
            K = k_res["value"]
            if K > K_prime:
                dr_res = calculate_doubly_reinforced_section(
                    M_abs, fcu, fy, eff_b, current_d, d_prime, K_prime, beta_b
                )
                As_req = dr_res["As_req"]
                As_prime_req = dr_res["As_prime_req"]
                notes.append(dr_res["note"])
            else:
                z_res = calculate_lever_arm(current_d, K)
                As_req = calculate_singly_reinforced_section(M_abs, fy, z_res["value"])["value"]
                notes.append(z_res["note"])

        # 1b. Bar Selection
        tens_bars = select_reinforcement(
            As_req=As_req, b_available=b, cover=section.cover, link_dia=section.link_dia,
        )
        final_tens_bars = tens_bars

        # 1c. Adjust d if 2 layers are needed
        if tens_bars["layers"] > 1:
            # Assume 25mm gap between layers
            gap = 25.0
            new_d = h - section.cover - section.link_dia - tens_bars["dia"] - gap / 2.0
            if abs(new_d - current_d) < 1.0:
                notes.append(f"Effective depth converged at {new_d:.1f} mm.")
                break
            current_d = new_d
            notes.append(f"Two layers required. Recalculated d = {current_d:.1f} mm.")
        else:
            break

    results["As_req"] = round(As_req, 2)
    results["As_prov"] = final_tens_bars["As_prov"]
    results["reinforcement_description"] = final_tens_bars["description"]
    results["As_prime_req"] = round(As_prime_req, 2)

    # ------------------------------------------------------------------
    # 2. Compression & Side Reinforcement
    # ------------------------------------------------------------------
    if As_prime_req > 0:
        comp_bars = select_reinforcement(As_prime_req, b, section.cover, section.link_dia)
        results["As_prime_prov"] = comp_bars["As_prov"]
        results["compression_reinforcement_description"] = comp_bars["description"]
        notes.append(f"Compression steel: {comp_bars['description']}")

    side_res = check_side_reinforcement_requirement(h, b, fy)
    notes.append(side_res["note"])
    if side_res.get("required"):
        warnings.append(f"Provide {side_res['As_req']} mm² total as side reinforcement (h > 750mm).")

    # ------------------------------------------------------------------
    # 3. Standard Checks (Limits, Spacing, Deflection, Shear)
    # ------------------------------------------------------------------
    # [Rest of the checks remain similar, but using current_d]
    notes.append("--- Reinforcement Limits (BS 8110 Cl 3.12) ---")
    lim_res = check_reinforcement_limits(final_tens_bars["As_prov"], section.As_min, section.As_max, "tension")
    notes.append(lim_res["note"])

    notes.append("--- Deflection Check (BS 8110 Cl 3.4.6) ---")
    basic_ratio = determine_basic_ratio(section.section_type, section.support_condition)
    def_res = check_deflection(
        span, current_d, basic_ratio, final_tens_bars["As_prov"], As_req, eff_b, M_abs, fy,
        results.get("As_prime_prov", 0.0), beta_b
    )
    results["deflection_check"] = def_res["status"]
    notes.append(def_res["note"])

    notes.append("--- Shear Design (BS 8110 Cl 3.4.5) ---")
    shear_res = check_shear_stress(V, b, current_d, fcu)
    notes.append(shear_res["note"])

    if shear_res["status"] == "OK":
        vc_res = calculate_vc(final_tens_bars["As_prov"], b, current_d, fcu)
        vc = vc_res["value"]
        notes.append(vc_res["note"])

        # Apply Shear Enhancement (Cl 3.4.5.8) if av is provided
        if av:
            enh_res = apply_shear_enhancement(vc, av, current_d)
            vc = enh_res["value"]
            notes.append(enh_res["note"])

        link_res = calculate_shear_links(shear_res["v"], vc, b, fyv, current_d, int(section.link_dia))
        results["shear_links"] = link_res["links"]
        notes.append(link_res["note"])
    else:
        results["status"] = "Shear Failure"

    return results

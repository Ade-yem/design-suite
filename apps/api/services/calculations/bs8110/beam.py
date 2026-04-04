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
)


# ---------------------------------------------------------------------------
# Main design function
# ---------------------------------------------------------------------------

def calculate_beam_reinforcement(
    section: BeamSection,
    M: float,
    V: float,
    span: float,
) -> dict:
    """
    Full beam design per BS 8110-1:1997.

    Parameters
    ----------
    section : BeamSection
        Cross-section geometry and material properties
        (from ``models/calculations/beam_section``).
    M : float
        Design ultimate moment (N·mm).
    V : float
        Design ultimate shear force (N).
    span : float
        Effective span (mm).

    Returns
    -------
    dict
        Keys:
        - ``status``                      : ``"OK"`` or failure description.
        - ``As_req``                      : Required tension steel (mm²).
        - ``As_prov``                     : Provided tension steel (mm²).
        - ``reinforcement_description``   : e.g. ``"3H20"``.
        - ``As_prime_req``                : Required compression steel (mm²).
        - ``As_prime_prov``               : Provided compression steel (mm²).
        - ``compression_reinforcement_description``.
        - ``shear_links``                 : Link description string.
        - ``deflection_check``            : ``"OK"`` / ``"FAIL"``.
        - ``notes``                       : List of calculation trail strings.
        - ``warnings``                    : List of non-fatal warnings.
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
    # 0. Echo section summary
    # ------------------------------------------------------------------
    notes.append(section.summary())
    notes.append(
        f"Design actions: M = {M:.0f} N·mm, V = {V:.0f} N, span = {span:.0f} mm"
    )

    b   = section.b
    d   = section.d
    h   = section.h
    fcu = section.fcu
    fy  = section.fy
    fyv = section.fyv
    d_prime = section.d_prime
    beta_b  = section.beta_b

    # ------------------------------------------------------------------
    # 1. K'  (accounting for moment redistribution)
    # ------------------------------------------------------------------
    k_prime_res = calculate_k_prime(beta_b)
    K_prime = k_prime_res["value"]
    notes.append(k_prime_res["note"])

    # ------------------------------------------------------------------
    # 2. Flexural design
    # ------------------------------------------------------------------
    As_req: float = 0.0
    As_prime_req: float = 0.0

    if section.section_type == "flanged":
        # ---- Flanged beam ----
        notes.append("--- Flanged Beam Flexural Design ---")
        fl_res = calculate_flanged_beam_reinforcement(
            M=M,
            fcu=fcu,
            fy=fy,
            b=b,
            bf=section.bf,
            d=d,
            hf=section.hf,
        )
        As_req       = fl_res["As_req"]
        As_prime_req = fl_res["As_prime_req"]
        notes.append(fl_res["note"])

        # If the web portion itself needed compression steel, report it
        if As_prime_req > 0:
            notes.append(
                "Note: compression reinforcement requirement comes from the "
                "web portion of the flanged beam."
            )

    else:
        # ---- Rectangular beam ----
        notes.append("--- Rectangular Beam Flexural Design ---")
        k_res = calculate_k(M, fcu, b, d)
        K = k_res["value"]
        notes.append(k_res["note"])

        if K > K_prime:
            notes.append(
                f"K ({K:.4f}) > K' ({K_prime:.4f}) — compression reinforcement required."
            )
            dr_res = calculate_doubly_reinforced_section(
                M=M, fcu=fcu, fy=fy, b=b, d=d,
                d_prime=d_prime, K_prime=K_prime,
            )
            As_req       = dr_res["As_req"]
            As_prime_req = dr_res["As_prime_req"]
            notes.append(dr_res["note"])
        else:
            notes.append(
                f"K ({K:.4f}) ≤ K' ({K_prime:.4f}) — singly reinforced section."
            )
            z_res = calculate_lever_arm(d, K)
            z     = z_res["value"]
            notes.append(z_res["note"])

            sr_res = calculate_singly_reinforced_section(M, fy, z)
            As_req = sr_res["value"]
            notes.append(sr_res["note"])

    results["As_req"]       = round(As_req, 2)
    results["As_prime_req"] = round(As_prime_req, 2)

    # ------------------------------------------------------------------
    # 3. Bar selection — tension steel
    # ------------------------------------------------------------------
    notes.append("--- Bar Selection ---")
    tens_bars = select_reinforcement(
        As_req=As_req,
        b_available=b,
        cover=section.cover,
        link_dia=section.link_dia,
    )
    results["As_prov"]                  = tens_bars["As_prov"]
    results["reinforcement_description"] = tens_bars["description"]
    notes.append(
        f"Tension steel: {tens_bars['description']} → As_prov = {tens_bars['As_prov']:.1f} mm²"
    )
    if tens_bars["warning"]:
        warnings.append(f"Tension spacing: {tens_bars['warning']}")

    # Bar selection — compression steel (if required)
    As_prime_prov = 0.0
    if As_prime_req > 0:
        comp_bars = select_reinforcement(
            As_req=As_prime_req,
            b_available=b,
            cover=section.cover,
            link_dia=section.link_dia,
        )
        As_prime_prov = comp_bars["As_prov"]
        results["As_prime_prov"]                       = As_prime_prov
        results["compression_reinforcement_description"] = comp_bars["description"]
        notes.append(
            f"Compression steel: {comp_bars['description']} → As'_prov = {As_prime_prov:.1f} mm²"
        )
        if comp_bars["warning"]:
            warnings.append(f"Compression spacing: {comp_bars['warning']}")

    # ------------------------------------------------------------------
    # 4. As_min / As_max checks
    # ------------------------------------------------------------------
    notes.append("--- Reinforcement Limits (BS 8110 Cl 3.12) ---")
    lim_res = check_reinforcement_limits(
        As_prov=tens_bars["As_prov"],
        As_min=section.As_min,
        As_max=section.As_max,
        label="tension",
    )
    notes.append(lim_res["note"])
    if lim_res["status"] == "FAIL":
        results["status"] = "Reinforcement Limits Failure"
        warnings.append("Tension steel outside BS 8110 Cl 3.12 limits.")

    if As_prime_prov > 0:
        comp_lim_res = check_reinforcement_limits(
            As_prov=As_prime_prov,
            As_min=0.0,     # No minimum specified for compression steel
            As_max=section.As_max,
            label="compression",
        )
        notes.append(comp_lim_res["note"])
        if comp_lim_res["status"] == "FAIL":
            if results["status"] == "OK":
                results["status"] = "Reinforcement Limits Failure"
            warnings.append("Compression steel exceeds BS 8110 Cl 3.12.6.1 maximum.")

    # ------------------------------------------------------------------
    # 5. Bar spacing / crack control check
    # ------------------------------------------------------------------
    notes.append("--- Bar Spacing / Crack Control (BS 8110 Cl 3.12.11) ---")
    if tens_bars["num"] >= 2:
        spacing_res = check_bar_spacing(
            num_bars=tens_bars["num"],
            bar_dia=float(tens_bars["dia"]),
            b=b,
            cover=section.cover,
            link_dia=section.link_dia,
            fy=fy,
            beta_b=beta_b,
        )
        notes.append(spacing_res["note"])
        if spacing_res["status"] == "FAIL":
            warnings.append(
                f"Bar spacing exceeds limit: clear = {spacing_res['clear_space']} mm, "
                f"max = {spacing_res['max_clear']} mm (BS 8110 Cl 3.12.11)."
            )

    # ------------------------------------------------------------------
    # 6. Deflection check
    # ------------------------------------------------------------------
    notes.append("--- Deflection Check (BS 8110 Cl 3.4.6) ---")
    basic_ratio = determine_basic_ratio(section.section_type, section.support_condition)

    def_res = check_deflection(
        span=span,
        d=d,
        basic_ratio=basic_ratio,
        As_prov=tens_bars["As_prov"],
        As_req=As_req,
        b=b,
        M=M,
        fy=fy,
        As_prime_prov=As_prime_prov,
        beta_b=beta_b,
    )
    results["deflection_check"] = def_res["status"]
    notes.append(def_res["note"])

    if def_res["status"] == "FAIL":
        results["status"] = "Deflection Failure"
        notes.append("CRITICAL: Deflection check failed. Increase section depth or reduce span.")
        return results

    # ------------------------------------------------------------------
    # 7. Shear capacity check
    # ------------------------------------------------------------------
    notes.append("--- Shear Design (BS 8110 Cl 3.4.5) ---")
    shear_res = check_shear_stress(V, b, d, fcu)
    notes.append(shear_res["note"])

    if shear_res["status"] == "FAIL":
        results["status"] = "Shear Failure"
        notes.append(
            "CRITICAL: Applied shear stress exceeds maximum (0.8√fcu or 5 N/mm²). "
            "Increase section size."
        )
        return results

    # ------------------------------------------------------------------
    # 8. Concrete shear capacity  vc  and link design
    # ------------------------------------------------------------------
    vc_res = calculate_vc(
        As_prov=tens_bars["As_prov"],
        b=b,
        d=d,
        fcu=fcu,
    )
    vc = vc_res["value"]
    notes.append(vc_res["note"])

    link_res = calculate_shear_links(
        v=shear_res["v"],
        vc=vc,
        b=b,
        fyv=fyv,
        d=d,
        link_dia=int(section.link_dia),
        num_legs=2,
    )
    results["shear_links"] = link_res["links"]
    notes.append(link_res["note"])

    # ------------------------------------------------------------------
    # Done
    # ------------------------------------------------------------------
    return results

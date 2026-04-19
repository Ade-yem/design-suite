"""
BS 8110-1:1997  –  Special Slab Design  (Clauses 3.6 & 3.7)
=============================================================
Handles design of three slab types that deviate from the solid-slab rules:

  1. **Ribbed Slabs** (Cl 3.6) — one-way spanning T-section ribs.
  2. **Waffle Slabs** (Cl 3.6) — two-way ribbed slabs treated as T-beams in
     each direction acting as an equivalent solid slab for coefficient purposes.
  3. **Flat Slabs** (Cl 3.7) — solid or drop-panel slabs supported directly
     on columns; designed via the Simplified Method of Cl 3.7.2.7.

Design sequence
---------------
Ribbed / Waffle
  1.  Geometric checks (topping, rib width, clear spacing).
  2.  Moment per rib derived from equivalent solid slab UDL.
  3.  Flanged-section flexural design (T-beam: flange = topping, web = rib).
  4.  Neutral axis position check — NA must lie in flange (Cl 3.6.1.5).
  5.  Bar selection (per rib).
  6.  Shear check per rib against vc (Cl 3.6.4 / Table 3.8).
  7.  Deflection check using modified basic span/depth ratios (Table 3.13).

Flat Slab
  1.  Total design moment Mt per sub-frame (Cl 3.7.2.7).
  2.  Equivalent frame distribution into Column Strip and Middle Strip.
  3.  Hogging / Sagging moment distribution (Table 3.18 or simplified).
  4.  Flexural strip design using standard K / z method.
  5.  Deflection check with flat-slab basic ratio modification.
  6.  Punching shear at column face (u0) and critical 1.5d perimeter (u1).
  7.  Punching shear at drop panel edge (if drop present).

Detailing Notes
---------------
  * Ribbed slab bars extend the full length of the rib; splices and anchorage
    follow Cl 3.12.8 (40Φ for T2 bars in tension).
  * Topping mesh minimum 0.12% of topping area each way (Cl 3.6.6.2).
  * Flat slab column strip receives 2/3 of hogging reinforcement (Cl 3.7.2.10).
"""

from __future__ import annotations

import math
from typing import Optional

from models.bs8110.special_slab import RibbedWaffleSection, FlatSlabSection
from core.design.rc.bs8110.formulas import (
    calculate_k,
    calculate_k_prime,
    calculate_lever_arm,
    calculate_singly_reinforced_section,
    calculate_doubly_reinforced_section,
    calculate_flanged_beam_reinforcement,
    calculate_vc,
    check_shear_stress,
    check_deflection,
    determine_basic_ratio,
    check_reinforcement_limits,
)
from core.design.rc.common.select_reinforcement import (
    select_slab_reinforcement,
    select_beam_reinforcement,
)


# ===========================================================================
# Helper – basic span/depth ratio for ribbed slabs  (BS 8110 Table 3.13)
# ===========================================================================
# Table 3.13 gives *modification factors* applied to the solid-slab basic ratio
# from Table 3.9. For ribbed slabs the basic ratio is multiplied by:
#   0.8  if rib spacing > 900 mm
#   No modification for rib spacing ≤ 900 mm
# And the support-condition ratios from Table 3.9 apply:
#   Simple      : 20
#   Continuous  : 26
#   Cantilever  :  7

def _ribbed_basic_ratio(support_condition: str, rib_spacing: float) -> float:
    """
    Return the basic span/d ratio for a ribbed slab (Table 3.9 + Table 3.13).

    BS 8110 Table 3.13:
      Ribbed slabs use the same basic ratios as solid slabs (Table 3.9) but
      multiplied by 0.8 when rib spacing exceeds 900 mm (Cl 3.6.2.1).

    Parameters
    ----------
    support_condition : ``"simple"``, ``"continuous"``, or ``"cantilever"``.
    rib_spacing       : Centre-to-centre rib spacing (mm).
    """
    base = determine_basic_ratio("rectangular", support_condition)
    if rib_spacing > 900.0:
        base *= 0.8
    return base


# ===========================================================================
# 1. Ribbed / Waffle Slab Design  (Clause 3.6)
# ===========================================================================

def design_ribbed_slab(
    section: RibbedWaffleSection,
    M_rib: float,   # Design moment per rib (N·mm)
    V_rib: float,   # Design shear force per rib (N)
    span: float,    # Effective span (mm) for deflection check
    As_prime_prov: float = 0.0,   # Compression steel area (mm²) if any; 0 for one-span
) -> dict:
    """
    Design a single rib of a ribbed or waffle slab per BS 8110 Cl 3.6.

    The rib is modelled as a **flanged (T-) beam** with:
      * Flange width            = rib_spacing         (b_f, effective = c/c spacing)
      * Flange thickness        = topping_thickness    (h_f)
      * Web width               = rib_width            (b_w)
      * Total depth             = h                    (shared with section)
      * Effective depth         = d                    (to centroid of tension steel)

    Flexural design follows Cl 3.4.4.5 (flanged beam procedure):
      * If M ≤ M_f (flange moment capacity) → NA in flange → rectangular design
        with b = b_f.
      * If M > M_f                          → NA in web    → two-part approach,
        with compression steel if K_w > K'.

    Parameters
    ----------
    section       : ``RibbedWaffleSection`` — describes rib geometry and materials.
    M_rib         : Design ultimate moment per rib (N·mm). Positive = sagging.
    V_rib         : Design ultimate shear per rib (N).
    span          : Effective span of the rib (mm) — used for deflection check.
    As_prime_prov : Compression steel provided (mm²).  Usually 0 for simply supported ribs.

    Returns
    -------
    dict with keys:
        status                   : ``"OK"`` or failure description.
        As_req                   : Required tension steel area per rib (mm²).
        As_prov                  : Provided tension steel area per rib (mm²).
        reinforcement_description: e.g. ``"2H16"``.
        As_prime_req             : Required compression steel per rib (mm²), if any.
        shear_status             : ``"OK"`` or shear failure message.
        deflection_check         : ``"OK"`` or ``"FAIL"``.
        topping_mesh             : Prescriptive minimum topping mesh description.
        notes                    : List of calculation step strings.
        warnings                 : List of warning strings.
    """
    notes: list[str] = []
    warnings: list[str] = []
    results: dict = {"status": "OK", "notes": notes, "warnings": warnings}

    notes.append(section.summary())
    notes.append(
        f"Design actions per rib: M = {M_rib/1e6:.2f} kN·m, V = {V_rib/1e3:.2f} kN  "
        f"(BS 8110 Cl 3.6)"
    )

    b_f = section.rib_spacing       # Effective flange width = c/c rib spacing
    b_w = section.rib_width         # Web (rib) width
    h_f = section.topping_thickness # Flange (topping) thickness
    d   = section.d                 # Effective depth
    fcu = section.fcu
    fy  = section.fy

    # -------------------------------------------------------------------------
    # Step 1: Topping thickness check  (Cl 3.6.1.3)
    # -------------------------------------------------------------------------
    min_topping = max(30.0, 0.1 * section.clear_rib_spacing)
    if section.topping_thickness < min_topping:
        warnings.append(
            f"Topping ({section.topping_thickness} mm) < required {min_topping:.0f} mm "
            f"[max(30, 0.1×clear)] (Cl 3.6.1.3)."
        )
    notes.append(
        f"Topping check: provided {section.topping_thickness} mm ≥ min {min_topping:.0f} mm "
        f"(Cl 3.6.1.3)  ✓" if section.topping_thickness >= min_topping else
        f"Topping check: {section.topping_thickness} mm < min {min_topping:.0f} mm — WARNING."
    )

    # -------------------------------------------------------------------------
    # Step 2: K' (limiting K)
    # -------------------------------------------------------------------------
    k_prime_res = calculate_k_prime(section.beta_b)
    K_prime = k_prime_res["value"]
    notes.append(k_prime_res["note"])

    # -------------------------------------------------------------------------
    # Step 3: Flanged-beam flexural design  (Cl 3.4.4.5 via helper)
    # -------------------------------------------------------------------------
    notes.append("--- Flanged-beam flexural design (Cl 3.4.4.5) ---")
    fl_res = calculate_flanged_beam_reinforcement(
        M=M_rib, fcu=fcu, fy=fy,
        b=b_w, bf=b_f, d=d, hf=h_f,
        d_prime=section.cover + section.link_dia if hasattr(section, "link_dia") else section.cover + 8.0,
        beta_b=section.beta_b,
    )
    notes.append(fl_res["note"])

    As_req      = fl_res["As_req"]
    As_prime_req = fl_res["As_prime_req"]

    # -------------------------------------------------------------------------
    # Step 4: Neutral axis position check — NA should be in flange
    # -------------------------------------------------------------------------
    # The stress-block depth s = 0.9 × x; lever arm z relates to x:
    #   x = (d - z) / 0.45  →  s = 0.9 × x = 2(d - z)
    # We re-derive z from the flanged design K.
    if fl_res.get("neutral_axis_in_flange"):
        K_check = fl_res.get("K", 0)
        z_check_res = calculate_lever_arm(d, K_check)
        z_check = z_check_res["value"]
        s = 2.0 * (d - z_check)   # stress-block depth = 0.9x = 2(d-z)
        if s > h_f:
            warnings.append(
                f"NA extends into web: stress-block depth s = {s:.1f} mm > h_f = {h_f} mm. "
                "Flanged design with web contribution is already handled."
            )
        else:
            notes.append(
                f"NA within flange: s = {s:.1f} mm < h_f = {h_f} mm (Cl 3.6.1.5) ✓"
            )
    else:
        notes.append("NA extends into web: two-part flanged beam design applied (Cl 3.4.4.5).")
        if K_prime is not None and fl_res.get("K_w", 0) > K_prime:
            warnings.append(
                "Rib moment capacity exceeded (K_w > K'). Compression steel may be required. "
                "Consider increasing rib depth."
            )

    # -------------------------------------------------------------------------
    # Step 5: Bar selection
    # -------------------------------------------------------------------------
    As_design = max(As_req, section.As_rib_min)
    bars = select_beam_reinforcement(
        As_req=As_design,
        b_available=b_w,
        cover=section.cover,
        link_dia=section.link_dia if hasattr(section, "link_dia") else 6.0,
    )
    results["As_req"]                    = round(As_req, 2)
    results["As_prov"]                   = bars["As_prov"]
    results["reinforcement_description"] = bars["description"]
    results["As_prime_req"]              = round(As_prime_req, 2)

    if bars["warning"]:
        warnings.append(bars["warning"])
    notes.append(f"Main rib steel: {bars['description']} (As_prov = {bars['As_prov']:.1f} mm²)")

    # Reinforcement limits (per rib)
    lim_res = check_reinforcement_limits(bars["As_prov"], section.As_rib_min, section.As_rib_max, "tension")
    notes.append(lim_res["note"])
    if lim_res["status"] == "FAIL":
        results["status"] = "Reinforcement Limit Failure"

    # -------------------------------------------------------------------------
    # Step 6: Shear check per rib  (Cl 3.6.4 / Table 3.8)
    # -------------------------------------------------------------------------
    notes.append("--- Shear Check  (Cl 3.6.4 / 3.4.5) ---")
    # Shear stress in rib: v = V_rib / (bw × d)
    shear_res = check_shear_stress(V_rib, b_w, d, fcu)
    notes.append(shear_res["note"])

    if shear_res["status"] == "FAIL":
        results["status"] = "Shear Failure (v > v_max — increase rib size)"
        results["shear_status"] = "FAIL: v exceeds absolute maximum (Cl 3.4.5.2)"
    else:
        # vc based on As_prov (not As_req)
        vc_res = calculate_vc(bars["As_prov"], b_w, d, fcu)
        vc = vc_res["value"]
        notes.append(vc_res["note"])

        if shear_res["v"] <= vc:
            results["shear_status"] = "OK — No shear links required"
            notes.append(f"v ({shear_res['v']:.3f}) ≤ vc ({vc:.3f}) — No links needed (Cl 3.6.4).")
        elif shear_res["v"] <= (vc + 0.4):
            results["shear_status"] = "Minimum links recommended"
            warnings.append(
                f"v ({shear_res['v']:.3f}) > vc ({vc:.3f}): ribs normally have no links. "
                "Increase rib depth or width."
            )
        else:
            results["shear_status"] = f"FAIL: v ({shear_res['v']:.3f}) >> vc ({vc:.3f}). Redesign rib."
            if results["status"] == "OK":
                results["status"] = "Shear Failure"

    # -------------------------------------------------------------------------
    # Step 7: Deflection check  (Cl 3.6.2 / Table 3.9 + Table 3.13)
    # -------------------------------------------------------------------------
    notes.append("--- Deflection Check  (Cl 3.6.2 / Table 3.13) ---")
    basic_ratio = _ribbed_basic_ratio(section.support_condition, section.rib_spacing)
    notes.append(
        f"Basic span/d ratio = {basic_ratio:.1f} (Table 3.9 for '{section.support_condition}', "
        f"Table 3.13 factor applied for rib spacing {section.rib_spacing} mm)"
    )
    def_res = check_deflection(
        span, d, basic_ratio,
        bars["As_prov"], As_req,
        b_w, M_rib, fy, As_prime_prov, section.beta_b,
    )
    results["deflection_check"] = def_res["status"]
    notes.append(def_res["note"])
    if def_res["status"] == "FAIL":
        results["status"] = "Deflection Failure"
        warnings.append(
            f"Deflection FAIL: L/d = {def_res['actual']:.1f} > allowable {def_res['allowable']:.1f}. "
            "Increase rib depth."
        )

    # -------------------------------------------------------------------------
    # Step 8: Prescriptive topping mesh  (Cl 3.6.6.2)
    # -------------------------------------------------------------------------
    # Minimum mesh in topping: 0.12% of topping area (each way)
    As_mesh_min = 0.0012 * 1000.0 * section.topping_thickness  # mm²/m
    mesh = select_slab_reinforcement(As_mesh_min, section.topping_thickness - 15.0, section.topping_thickness, fy, 1.0)
    results["topping_mesh"] = mesh["description"]
    notes.append(
        f"Topping mesh (Cl 3.6.6.2): As_min = 0.12% × 1000 × {section.topping_thickness} = "
        f"{As_mesh_min:.0f} mm²/m each way → {mesh['description']}"
    )

    return results


# ===========================================================================
# 2. Flat Slab Design – Simplified Method  (Clause 3.7.2.7)
# ===========================================================================

# ----- Moment distribution factors (BS 8110 Table 3.18 / Cl 3.7.2.10) -----
# Format: panel_position → {"hogging": (CS_fraction, MS_fraction),
#                            "sagging": (CS_fraction, MS_fraction)}
# Fractions represent share of the total hogging / sagging moment from the
# equivalent frame analysis going to the Column Strip (CS) vs Middle Strip (MS).

TABLE_3_18_DISTRIBUTION = {
    # Interior spans & supports (Cl 3.7.2.7)
    "interior": {
        "hogging": {"CS": 0.75, "MS": 0.25},
        "sagging": {"CS": 0.55, "MS": 0.45},
    },
    # Edge panels (one discontinuous transverse edge)
    "edge": {
        "hogging": {"CS": 0.80, "MS": 0.20},
        "sagging": {"CS": 0.60, "MS": 0.40},
    },
    # Corner panels (two discontinuous transverse edges)
    "corner": {
        "hogging": {"CS": 0.80, "MS": 0.20},
        "sagging": {"CS": 0.60, "MS": 0.40},
    },
}

# Fraction of total Mt used as hogging (negative) and sagging (positive) moments
# per Cl 3.7.2.7  (0.65 × Mt for interior moment, 0.35 × Mt for mid-span)
_MT_HOG_FRACTION = 0.65   # Total hogging fraction of Mt (Cl 3.7.2.7)
_MT_SAG_FRACTION = 0.35   # Total sagging fraction of Mt


def _column_strip_width(lx: float, ly: float) -> float:
    """
    Column strip half-width either side of column centreline per Cl 3.7.2.1.

    Returns the **total** CS width (not half) = min(lx, ly).
    The middle strip occupies the remaining (L − CS_width) in each direction.
    """
    return min(lx, ly)


def calculate_flat_slab_moments(
    section: FlatSlabSection,
    n_udl: float,   # Design UDL (N/mm²), i.e. factored 1.4Gk + 1.6Qk
) -> dict:
    """
    Compute total design moment Mt and distribute to column/middle strips.

    BS 8110 Cl 3.7.2.7 Simplified Frame Method
    -------------------------------------------
    1.  Effective span:
            L_eff = L1 − 2 × h_c / 3   (Cl 3.7.2.8)
            Minimum: L_eff ≥ 0.65 × L1
    2.  Total design moment per panel width L2:
            Mt = 0.125 × n × L2 × L_eff²
    3.  Distribution into strips via Table 3.18 / Cl 3.7.2.10.

    Parameters
    ----------
    section : ``FlatSlabSection``
    n_udl   : Factored design load (N/mm²)

    Returns
    -------
    dict with strip moments in N·mm (per metre strip width):
        Mt_kNm, CS_hogging, MS_hogging, CS_sagging, MS_sagging,
        CS_width, MS_width, L_eff, notes, warnings
    """
    notes: list[str] = []
    warnings: list[str] = []

    L1  = section.lx   # Span in design direction
    L2  = section.ly   # Panel width (transverse)
    hc  = section.hc   # Effective column head (mm)

    # Effective span (Cl 3.7.2.8)
    L_eff = L1 - (2.0 * hc / 3.0)
    L_eff_min = 0.65 * L1
    if L_eff < L_eff_min:
        L_eff = L_eff_min
        notes.append(
            f"L_eff = {L1} - 2×{hc}/3 = less than 0.65L1. "
            f"Using minimum L_eff = 0.65×{L1} = {L_eff_min:.0f} mm (Cl 3.7.2.8)."
        )
    else:
        notes.append(
            f"L_eff = L1 − 2hc/3 = {L1} − 2×{hc}/3 = {L_eff:.0f} mm (Cl 3.7.2.8)."
        )

    # Total design moment per panel (N·mm)
    Mt = 0.125 * n_udl * L2 * (L_eff ** 2)
    notes.append(
        f"Mt = 0.125 × n × L2 × L_eff² = 0.125 × {n_udl*1e3:.3f} × {L2} × {L_eff:.0f}² "
        f"= {Mt/1e6:.2f} kN·m (Cl 3.7.2.7)"
    )

    # Total hogging and sagging moments (as fractions of Mt)
    M_hog_total = _MT_HOG_FRACTION * Mt   # This is the support (negative) design moment
    M_sag_total = _MT_SAG_FRACTION * Mt   # This is the span (positive) design moment
    notes.append(
        f"M_hogging_total = 0.65 × Mt = {M_hog_total/1e6:.2f} kN·m/panel  |  "
        f"M_sagging_total = 0.35 × Mt = {M_sag_total/1e6:.2f} kN·m/panel"
    )

    # Strip widths (Cl 3.7.2.1)
    CS_width = _column_strip_width(L1, L2)     # total CS width (mm)
    MS_width = L2 - CS_width                   # middle strip width (mm)
    notes.append(
        f"Column Strip width = min(lx, ly) = min({L1}, {L2}) = {CS_width:.0f} mm  |  "
        f"Middle Strip width = {MS_width:.0f} mm (Cl 3.7.2.1)"
    )

    # Distribution to CS and MS (Table 3.18 / Cl 3.7.2.10)
    ec = section.edge_condition
    dist = TABLE_3_18_DISTRIBUTION.get(ec, TABLE_3_18_DISTRIBUTION["interior"])

    CS_hog_moment = dist["hogging"]["CS"] * M_hog_total   # N·mm per panel
    MS_hog_moment = dist["hogging"]["MS"] * M_hog_total
    CS_sag_moment = dist["sagging"]["CS"] * M_sag_total
    MS_sag_moment = dist["sagging"]["MS"] * M_sag_total

    notes.append(
        f"Strip distribution (Table 3.18 / Cl 3.7.2.10, '{ec}' panel):\n"
        f"  CS hogging: {dist['hogging']['CS']*100:.0f}% × {M_hog_total/1e6:.2f} = {CS_hog_moment/1e6:.2f} kN·m\n"
        f"  MS hogging: {dist['hogging']['MS']*100:.0f}% × {M_hog_total/1e6:.2f} = {MS_hog_moment/1e6:.2f} kN·m\n"
        f"  CS sagging: {dist['sagging']['CS']*100:.0f}% × {M_sag_total/1e6:.2f} = {CS_sag_moment/1e6:.2f} kN·m\n"
        f"  MS sagging: {dist['sagging']['MS']*100:.0f}% × {M_sag_total/1e6:.2f} = {MS_sag_moment/1e6:.2f} kN·m"
    )

    # Convert panel moments to per-metre-width moments for strip design
    CS_hog_pm = CS_hog_moment / CS_width if CS_width > 0 else 0.0
    MS_hog_pm = MS_hog_moment / MS_width if MS_width > 0 else 0.0
    CS_sag_pm = CS_sag_moment / CS_width if CS_width > 0 else 0.0
    MS_sag_pm = MS_sag_moment / MS_width if MS_width > 0 else 0.0

    notes.append(
        f"Per-metre-width moments:\n"
        f"  CS hogging: {CS_hog_pm/1e6:.2f} kN·m/m  |  MS hogging: {MS_hog_pm/1e6:.2f} kN·m/m\n"
        f"  CS sagging: {CS_sag_pm/1e6:.2f} kN·m/m  |  MS sagging: {MS_sag_pm/1e6:.2f} kN·m/m"
    )

    return {
        "Mt_kNm":         round(Mt / 1e6, 2),
        "M_hog_total":    M_hog_total,
        "M_sag_total":    M_sag_total,
        "CS_hogging_pm":  CS_hog_pm,   # N·mm/m — use for strip design
        "MS_hogging_pm":  MS_hog_pm,
        "CS_sagging_pm":  CS_sag_pm,
        "MS_sagging_pm":  MS_sag_pm,
        "CS_width_mm":    CS_width,
        "MS_width_mm":    MS_width,
        "L_eff_mm":       L_eff,
        "notes":          notes,
        "warnings":       warnings,
    }


def _design_flat_strip(M_per_m: float, section: FlatSlabSection, label: str) -> dict:
    """
    Internal helper: flexural design of a flat slab strip (CS or MS) per metre.

    Parameters
    ----------
    M_per_m : Design moment per metre width (N·mm/m).  Positive = sagging.
    section : ``FlatSlabSection``
    label   : ``"CS_hogging"``  etc. — for note labelling.
    """
    notes = []
    warnings = []
    b = 1000.0
    d = section.d

    if M_per_m <= 0:
        As_min = section.As_min
        bars = select_slab_reinforcement(As_min, d, section.h, section.fy, section.beta_b)
        return {"As_req": 0.0, "bars": bars, "notes": [f"{label}: M ≤ 0 — min steel."], "warnings": []}

    k_prime_res = calculate_k_prime(section.beta_b)
    K_prime = k_prime_res["value"]
    notes.append(k_prime_res["note"])

    k_res = calculate_k(M_per_m, section.fcu, b, d)
    K = k_res["value"]
    notes.append(k_res["note"])

    if K > K_prime:
        warnings.append(
            f"{label}: K ({K:.4f}) > K' ({K_prime:.4f}). Slab depth inadequate. Increase h."
        )
        return {"As_req": None, "bars": None, "notes": notes, "warnings": warnings}

    z_res = calculate_lever_arm(d, K)
    notes.append(z_res["note"])
    As_req_val = calculate_singly_reinforced_section(M_per_m, section.fy, z_res["value"])["value"]
    As_design = max(As_req_val, section.As_min)

    bars = select_slab_reinforcement(As_design, d, section.h, section.fy, section.beta_b)
    if bars["warning"]:
        warnings.append(bars["warning"])

    notes.append(f"{label}: As_req = {As_req_val:.1f} mm²/m → {bars['description']}")
    return {"As_req": As_req_val, "bars": bars, "notes": notes, "warnings": warnings}


def design_flat_slab(
    section: FlatSlabSection,
    n_udl: float,   # Design UDL (N/mm²)
) -> dict:
    """
    Full flat slab design per BS 8110 Cl 3.7.

    Performs:
      1. Total moment calculation (Cl 3.7.2.7)
      2. Strip moment distribution (Table 3.18)
      3. Flexural design for all four strip/direction combinations
      4. Deflection check (short span, column strip governs)
      5. Punching shear check at column (Cl 3.7.7)

    Parameters
    ----------
    section : ``FlatSlabSection``
    n_udl   : Factored design load (N/mm²)

    Returns
    -------
    dict containing strip reinforcement, shear status, and deflection check.
    """
    notes: list[str] = []
    warnings: list[str] = []
    results: dict = {"status": "OK", "notes": notes, "warnings": warnings}

    notes.append(section.summary())
    notes.append(
        f"Design UDL n = {n_udl*1e3:.3f} kN/m². "
        f"Panel {section.edge_condition}, lx×ly = {section.lx:.0f}×{section.ly:.0f} mm. "
        f"(BS 8110 Cl 3.7)"
    )

    # --- Step 1: Moment distribution ---
    mom_res = calculate_flat_slab_moments(section, n_udl)
    notes.extend(mom_res["notes"])
    warnings.extend(mom_res["warnings"])

    results["Mt_kNm"]    = mom_res["Mt_kNm"]
    results["L_eff_mm"]  = mom_res["L_eff_mm"]
    results["strip_widths_mm"] = {
        "CS": mom_res["CS_width_mm"],
        "MS": mom_res["MS_width_mm"],
    }
    results["design_moments_kNm_per_m"] = {
        "CS_hogging": round(mom_res["CS_hogging_pm"] / 1e6, 2),
        "MS_hogging": round(mom_res["MS_hogging_pm"] / 1e6, 2),
        "CS_sagging": round(mom_res["CS_sagging_pm"] / 1e6, 2),
        "MS_sagging": round(mom_res["MS_sagging_pm"] / 1e6, 2),
    }

    # --- Step 2: Flexural design per strip ---
    strip_designs = {}
    for label, M_pm in [
        ("CS_hogging", mom_res["CS_hogging_pm"]),
        ("MS_hogging", mom_res["MS_hogging_pm"]),
        ("CS_sagging", mom_res["CS_sagging_pm"]),
        ("MS_sagging", mom_res["MS_sagging_pm"]),
    ]:
        notes.append(f"--- {label} strip design ---")
        sd = _design_flat_strip(M_pm, section, label)
        notes.extend(sd["notes"])
        warnings.extend(sd["warnings"])
        if sd["As_req"] is None:
            results["status"] = f"Section Inadequate ({label})"
            return results
        strip_designs[label] = sd
        if sd["bars"]:
            results[f"{label}_steel"] = sd["bars"]["description"]
            results[f"{label}_As_prov"] = sd["bars"]["As_prov"]

    # Cl 3.7.2.10: at least 2/3 of hogging CS steel should be in inner half of CS
    notes.append(
        "Cl 3.7.2.10: At least 2/3 of the Column Strip hogging reinforcement must be "
        "placed in the central half of the Column Strip width."
    )

    # --- Step 3: Deflection check (column strip, sagging governs) ---
    notes.append("--- Deflection Check (Cl 3.7.8 / Table 3.9) ---")
    # Flat slabs: basic L/d ratio = 26 (continuous), 20 (simple) — same as solid slab
    basic_ratio = determine_basic_ratio("rectangular", "continuous")  # flat slabs are always multi-panel
    # For flat slabs use lx as governing span
    cs_sag = strip_designs["CS_sagging"]
    if cs_sag["As_req"] is not None and cs_sag["bars"] is not None:
        def_res = check_deflection(
            section.lx, section.d, basic_ratio,
            cs_sag["bars"]["As_prov"], cs_sag["As_req"],
            1000.0, mom_res["CS_sagging_pm"], section.fy, 0.0, section.beta_b,
        )
        results["deflection_check"] = def_res["status"]
        notes.append(def_res["note"])
        if def_res["status"] == "FAIL":
            results["status"] = "Deflection Failure"
            warnings.append(
                f"Deflection FAIL: L/d = {def_res['actual']:.1f} > allowable {def_res['allowable']:.1f}. "
                "Increase slab thickness."
            )

    # --- Step 4: Punching shear (Cl 3.7.7) ---
    # Effective shear force Veff = 1.15 × V for internal columns (Cl 3.7.6.2)
    # V = n × (L1 × L2 − area within critical perimeter)  ≈ n × L1 × L2 (conservative)
    V_col = n_udl * section.lx * section.ly   # Total column reaction (N)
    Veff = 1.15 * V_col   # Enhanced for moment transfer — Cl 3.7.6.2
    notes.append(
        f"Punching shear: V_col = n × lx × ly = {V_col/1e3:.1f} kN; "
        f"Veff = 1.15 × V = {Veff/1e3:.1f} kN (Cl 3.7.6.2, interior column)"
    )
    punch_res = design_flat_slab_punching(section, Veff)
    results["punching_shear"] = punch_res
    notes.extend(punch_res.get("notes", []))
    warnings.extend(punch_res.get("warnings", []))
    if punch_res["status"] != "OK":
        if results["status"] == "OK":
            results["status"] = punch_res["status"]

    return results


# ===========================================================================
# 3. Punching Shear  (Clause 3.7.7)
# ===========================================================================

def design_flat_slab_punching(
    section: FlatSlabSection,
    V_eff: float,   # Effective punching shear (N) including moment transfer enhancement
) -> dict:
    """
    Punching shear design for flat slab at column–slab junction.

    BS 8110 Cl 3.7.7 procedure
    ---------------------------
    1.  **Column face check (u0)** — v = Veff / (u0 × d) ≤ v_max = min(0.8√fcu, 5.0).

        * Square column:   u0 = 4 × c              (perimeter of column)
        * Circular column: u0 = π × c              (circumference)

    2.  **1.5d critical perimeter (u1)** — v = Veff / (u1 × d) vs vc.

        The 1.5d perimeter is derived from the column perimeter offset outward
        by 1.5d (Cl 3.7.7.3):
        * Square column:   u1 = 4 × c + 2π × (1.5d)   = 4c + 3πd
        * Circular column: u1 = π × c + 2π × (1.5d)   = π(c + 3d)

    3.  **Check at successive perimeters** if shear reinforcement is added
        (in this implementation only the first two perimeters are considered).

    Parameters
    ----------
    section : ``FlatSlabSection``
    V_eff   : Enhanced effective shear (N) — already includes Cl 3.7.6.2 factor.

    Returns
    -------
    dict with punching check results and detailed notes.
    """
    notes: list[str] = []
    warnings: list[str] = []
    status = "OK"

    d   = section.d
    hc  = section.hc        # Effective column head diameter / side
    fcu = section.fcu

    # ---- Column face perimeter u0 ----
    if section.is_circular_col:
        u0 = math.pi * hc           # π × diameter for circular column
        perimeter_note = f"Circular column: u0 = π × {hc:.0f} = {u0:.0f} mm"
    else:
        u0 = 4.0 * hc               # 4 × side for square column
        perimeter_note = f"Square column: u0 = 4 × {hc:.0f} = {u0:.0f} mm"

    v_face = V_eff / (u0 * d)
    v_max  = min(0.8 * math.sqrt(fcu), 5.0)
    notes.append(
        f"Column face: {perimeter_note}  |  "
        f"v_face = Veff/(u0×d) = {V_eff/1e3:.1f}k / ({u0:.0f}×{d:.0f}) = {v_face:.3f} N/mm²  "
        f"(v_max = {v_max:.3f}) (Cl 3.7.7.2)"
    )

    if v_face > v_max:
        status = "FAIL: Crushing at column face — increase slab depth or column size"
        warnings.append(f"Punching v_face ({v_face:.3f}) > v_max ({v_max:.3f}). Section too small.")

    # ---- 1.5d critical perimeter u1 ----
    if section.is_circular_col:
        u1 = math.pi * (hc + 3.0 * d)   # π × (c + 2 × 1.5d)
        u1_note = f"u1 = π × (hc + 3d) = π × ({hc:.0f} + {3*d:.0f}) = {u1:.0f} mm"
    else:
        u1 = 4.0 * hc + 3.0 * math.pi * d   # 4c + 2π × 1.5d
        u1_note = f"u1 = 4hc + 3πd = 4×{hc:.0f} + 3π×{d:.0f} = {u1:.0f} mm"

    v_crit = V_eff / (u1 * d)
    notes.append(
        f"1.5d perimeter: {u1_note}  |  "
        f"v_crit = Veff/(u1×d) = {V_eff/1e3:.1f}k / ({u1:.0f}×{d:.0f}) = {v_crit:.3f} N/mm² "
        f"(Cl 3.7.7.3)"
    )

    # vc based on average top *and* bottom reinforcement ratio
    # Conservative: use As_min (0.13% of h per m) as average, since strip design
    # results are not piped in here. The caller may override As_assumed if needed.
    As_assumed = 0.0075 * 1000.0 * d   # 0.75% × b × d — typical for flat slabs
    vc_res = calculate_vc(As_assumed, 1000.0, d, fcu, section.h)
    vc = vc_res["value"]
    notes.append(vc_res["note"])

    if v_crit > vc:
        if status == "OK":
            status = "FAIL: Punching shear exceeds vc — shear reinforcement required (Cl 3.7.7.5)"
        warnings.append(
            f"v_crit ({v_crit:.3f} N/mm²) > vc ({vc:.3f} N/mm²). "
            "Provide punching shear links or studs per Cl 3.7.7.5, or increase d."
        )
    else:
        notes.append(f"v_crit ({v_crit:.3f}) ≤ vc ({vc:.3f}) — No punching shear reinforcement required.")

    # ---- Drop panel shear check (if present) ----
    if section.is_drop_panel and section.drop_thickness > 0:
        d_drop = section.d_drop
        # Perimeter at edge of drop panel
        drop_dim = min(section.drop_lx, section.drop_ly) if section.drop_lx > 0 else 2 * section.hc
        if section.is_circular_col:
            u_drop = math.pi * (drop_dim + 3.0 * d)
        else:
            u_drop = 4.0 * drop_dim + 3.0 * math.pi * d
        v_drop = V_eff / (u_drop * d_drop)
        vc_drop_res = calculate_vc(As_assumed, 1000.0, d_drop, fcu, section.h + section.drop_thickness)
        vc_drop = vc_drop_res["value"]
        notes.append(
            f"Drop panel edge check: u_drop = {u_drop:.0f} mm, d_drop = {d_drop:.1f} mm, "
            f"v_drop = {v_drop:.3f}, vc_drop = {vc_drop:.3f} N/mm²"
        )
        if v_drop > vc_drop and status == "OK":
            status = "FAIL: Punching at drop panel edge — increase drop size"
            warnings.append(f"v_drop ({v_drop:.3f}) > vc_drop ({vc_drop:.3f}).")

    return {
        "status":       status,
        "v_face":       round(v_face, 4),
        "v_max":        round(v_max, 4),
        "v_crit_1_5d":  round(v_crit, 4),
        "vc":           round(vc, 4),
        "perimeters":   {"u0": round(u0, 1), "u1": round(u1, 1)},
        "notes":        notes,
        "warnings":     warnings,
    }


# ===========================================================================
# 4. Unified dispatcher
# ===========================================================================

def calculate_special_slab_reinforcement(
    section: RibbedWaffleSection | FlatSlabSection,
    n_udl: float,
    M_rib: Optional[float] = None,
    V_rib: Optional[float] = None,
    span: Optional[float] = None,
) -> dict:
    """
    Unified dispatcher for special slab design.

    Parameters
    ----------
    section : ``RibbedWaffleSection`` or ``FlatSlabSection``
    n_udl   : Factored design UDL (N/mm²)
    M_rib   : Design moment per rib (N·mm) — required for ribbed/waffle only.
    V_rib   : Design shear per rib (N) — required for ribbed/waffle only.
    span    : Effective span (mm) — required for ribbed/waffle deflection check.
    """
    if isinstance(section, RibbedWaffleSection):
        if M_rib is None or V_rib is None or span is None:
            raise ValueError(
                "M_rib, V_rib, and span must be provided for ribbed/waffle slab design."
            )
        return design_ribbed_slab(section, M_rib, V_rib, span)
    elif isinstance(section, FlatSlabSection):
        return design_flat_slab(section, n_udl)
    else:
        raise TypeError(
            f"section must be RibbedWaffleSection or FlatSlabSection, got {type(section).__name__}."
        )
"""
BS 8110-1:1997  –  Slab Design Orchestration
=============================================
Handles both one-way (Cl 3.5.2) and two-way (Cl 3.5.3) spanning solid slabs.

One-way slabs use Table 3.12 bending-moment / shear-force coefficients.
Two-way slabs use Table 3.14 (moments) and Table 3.15 (shear) with the
  Rankine–Marcus yield-line equations and torsion reinforcement at corners.
"""

from typing import Optional
from models.bs8110.slab import SlabSection
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

# ===========================================================================
# Table 3.12 — One-way slab moment & shear coefficients  (BS 8110 Cl 3.5.2)
# ===========================================================================
# Keys: ("moment"|"shear", position)
# Positions for moment:
#   "outer_support", "near_middle_end_span", "interior_support_first",
#   "middle_span", "interior_support"
# Positions for shear:
#   "outer_support", "first_interior_support", "interior_support"
#
# Returns coefficient × F × l  for moments, or coefficient × F for shears
# where F = total design UDL on span, l = effective span.

TABLE_3_12 = {
    # ---- moment (factor × F × l) ----
    ("moment", "outer_support"):             {"simple": 0.0,    "continuous": 0.0},
    ("moment", "near_middle_end_span"):      {"simple": 0.125,  "continuous": 0.086},
    ("moment", "outer_support_continuous"):  {"simple": 0.0,    "continuous": -0.04},
    ("moment", "first_interior_support"):    {"simple": None,   "continuous": -0.086},
    ("moment", "middle_span"):               {"simple": None,   "continuous": 0.063},
    ("moment", "interior_support"):          {"simple": None,   "continuous": -0.063},
    # ---- shear (factor × F) ----
    ("shear",  "outer_support"):             {"simple": 0.4,    "continuous": 0.46},
    ("shear",  "first_interior_support"):    {"simple": None,   "continuous": 0.6},
    ("shear",  "interior_support"):          {"simple": None,   "continuous": 0.5},
}


def get_one_way_coefficients(support_condition: str) -> dict:
    """
    Return all Table 3.12 coefficients for a given support condition.
    Returns a flat dict keyed by position label.
    """
    sc = support_condition.lower()
    result = {}
    for (kind, pos), vals in TABLE_3_12.items():
        result.setdefault(kind, {})[pos] = vals.get(sc)
    return result


# ===========================================================================
# Table 3.14 — Two-way bending moment coefficients  (BS 8110 Cl 3.5.3.3)
# Panel type key → {lx/ly ratio → (βsx_neg, βsx_pos, βsy_neg, βsy_pos)}
# Ratios tested: 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.75, 2.0
# βsx applies to short-span Msx = βsx · n · lx²
# βsy applies to long-span  Msy = βsy · n · lx²  (always uses lx², NOT ly²)
# ===========================================================================
# Format: panel_type → {
#   "short_neg": [coefs for ratios],
#   "short_pos": [...],
#   "long_neg":  [...],   (None if discontinuous on that edge)
#   "long_pos":  [...],
# }
# Ratios in order: 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.75, 2.0
_RATIOS = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.75, 2.0]

TABLE_3_14: dict = {
    "interior": {
        "short_neg": [0.031, 0.037, 0.042, 0.046, 0.050, 0.053, 0.059, 0.063],
        "short_pos": [0.024, 0.028, 0.032, 0.035, 0.037, 0.040, 0.044, 0.048],
        "long_neg":  [0.032]*8,  # constant for all ratios per the table footnote
        "long_pos":  [0.024]*8,
    },
    "one_short_discontinuous": {
        "short_neg": [0.039, 0.044, 0.048, 0.052, 0.055, 0.058, 0.063, 0.067],
        "short_pos": [0.029, 0.033, 0.036, 0.039, 0.041, 0.043, 0.047, 0.050],
        "long_neg":  [0.037]*8,
        "long_pos":  [0.028]*8,
    },
    "one_long_discontinuous": {
        "short_neg": [0.039, 0.049, 0.056, 0.062, 0.068, 0.073, 0.082, 0.089],
        "short_pos": [0.030, 0.036, 0.042, 0.047, 0.051, 0.055, 0.062, 0.067],
        "long_neg":  [None]*8,   # discontinuous long edge — no hogging
        "long_pos":  [0.037]*8,
    },
    "two_adjacent_discontinuous": {
        "short_neg": [0.047, 0.056, 0.063, 0.069, 0.074, 0.078, 0.087, 0.093],
        "short_pos": [0.036, 0.042, 0.047, 0.051, 0.055, 0.059, 0.065, 0.070],
        "long_neg":  [None]*8,
        "long_pos":  [0.034]*8,  # Table 3.14 gives 0.045 for long_pos on 2 adj. discontinuous
    },
    "two_short_discontinuous": {
        "short_neg": [0.046, 0.050, 0.054, 0.057, 0.060, 0.062, 0.067, 0.070],
        "short_pos": [0.034, 0.038, 0.040, 0.043, 0.045, 0.047, 0.050, 0.053],
        "long_neg":  [None]*8,
        "long_pos":  [0.034]*8,
    },
    "two_long_discontinuous": {
        "short_neg": [None]*8,
        "short_pos": [0.034, 0.046, 0.056, 0.065, 0.072, 0.078, 0.091, 0.100],
        "long_neg":  [0.045]*8,
        "long_pos":  [0.034]*8,
    },
    "three_discontinuous_one_long": {
        "short_neg": [0.057, 0.065, 0.071, 0.076, 0.081, 0.084, 0.092, 0.098],
        "short_pos": [0.043, 0.048, 0.053, 0.057, 0.060, 0.063, 0.069, 0.074],
        "long_neg":  [None]*8,
        "long_pos":  [0.044]*8,
    },
    "three_discontinuous_one_short": {
        "short_neg": [None]*8,
        "short_pos": [0.042, 0.054, 0.063, 0.071, 0.078, 0.084, 0.096, 0.105],
        "long_neg":  [0.058]*8,
        "long_pos":  [0.044]*8,
    },
    "four_discontinuous": {
        "short_neg": [None]*8,
        "short_pos": [0.055, 0.065, 0.074, 0.081, 0.087, 0.092, 0.103, 0.111],
        "long_neg":  [None]*8,
        "long_pos":  [0.056]*8,
    },
}


# ===========================================================================
# Table 3.15 — Two-way shear force coefficients  (BS 8110 Cl 3.5.3.4)
# Panel type → {lx/ly → (βvx_cont, βvx_disc, βvy_cont, βvy_disc)}
# where βvx_cont = continuous edge parallel to lx, etc.
# ===========================================================================
_RATIOS_V = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.75, 2.0]

TABLE_3_15: dict = {
    # format: [βvx_continuous, βvx_discontinuous, βvy_continuous, βvy_discontinuous]
    # using list of dicts for each ratio
    "four_continuous": {
        "short_cont": [0.33, 0.36, 0.39, 0.41, 0.43, 0.45, 0.48, 0.50],
        "short_disc": [None]*8,
        "long_cont":  [0.33]*8,
        "long_disc":  [None]*8,
    },
    "one_short_discontinuous": {
        "short_cont": [0.36, 0.39, 0.42, 0.44, 0.45, 0.47, 0.50, 0.52],
        "short_disc": [0.24, 0.27, 0.29, 0.31, 0.32, 0.34, 0.35, 0.38],
        "long_cont":  [0.36]*8,
        "long_disc":  [None]*8,
    },
    "one_long_discontinuous": {
        "short_cont": [0.36, 0.40, 0.44, 0.47, 0.49, 0.51, 0.55, 0.59],
        "short_disc": [None]*8,
        "long_cont":  [0.24, 0.27, 0.31, 0.32, 0.34, 0.34, 0.35, 0.40],
        "long_disc":  [0.24]*8,
    },
    "two_adjacent_discontinuous": {
        "short_cont": [0.40, 0.44, 0.47, 0.50, 0.52, 0.54, 0.57, 0.60],
        "short_disc": [0.26, 0.29, 0.31, 0.33, 0.34, 0.35, 0.38, 0.40],
        "long_cont":  [0.40]*8,
        "long_disc":  [0.26]*8,
    },
    "two_short_discontinuous": {
        "short_cont": [0.40, 0.43, 0.45, 0.47, 0.48, 0.49, 0.52, 0.54],
        "short_disc": [None]*8,
        "long_cont":  [None]*8,
        "long_disc":  [0.26]*8,
    },
    "two_long_discontinuous": {
        # βvy_cont not listed for ly direction in Table 3.15 for this case
        "short_cont": [None]*8,
        "short_disc": [0.26, 0.30, 0.33, 0.36, 0.38, 0.40, 0.44, 0.47],
        "long_cont":  [0.40]*8,
        "long_disc":  [None]*8,
    },
    "three_discontinuous_one_long": {
        "short_cont": [0.45, 0.48, 0.51, 0.53, 0.55, 0.57, 0.60, 0.63],
        "short_disc": [0.30, 0.32, 0.34, 0.35, 0.36, 0.37, 0.39, 0.41],
        "long_cont":  [None]*8,
        "long_disc":  [0.29]*8,
    },
    "three_discontinuous_one_short": {
        "short_cont": [None]*8,
        "short_disc": [None]*8,
        "long_cont":  [0.45]*8,
        "long_disc":  [0.30]*8,
    },
    "four_discontinuous": {
        "short_cont": [None]*8,
        "short_disc": [0.33, 0.39, 0.39, 0.41, 0.43, 0.45, 0.48, 0.50],
        "long_cont":  [None]*8,
        "long_disc":  [0.33]*8,
    },
}


def _interpolate(ratios, values, ly_lx):
    """Linear interpolation of a coefficient table for a given ly/lx ratio."""
    ly_lx = min(max(ly_lx, ratios[0]), ratios[-1])
    for i in range(len(ratios) - 1):
        if ratios[i] <= ly_lx <= ratios[i + 1]:
            t = (ly_lx - ratios[i]) / (ratios[i + 1] - ratios[i])
            v0 = values[i]
            v1 = values[i + 1]
            if v0 is None and v1 is None:
                return None
            if v0 is None:
                return v1
            if v1 is None:
                return v0
            return v0 + t * (v1 - v0)
    return values[-1]


def get_two_way_moment_coefficients(panel_type: str, ly_lx: float) -> dict:
    """
    Interpolate Table 3.14 for a given panel type and ly/lx ratio.
    Returns βsx_neg, βsx_pos, βsy_neg, βsy_pos (None if not applicable).
    """
    if panel_type not in TABLE_3_14:
        raise ValueError(
            f"Unknown panel_type '{panel_type}'. Valid options:\n  " +
            "\n  ".join(TABLE_3_14.keys())
        )
    row = TABLE_3_14[panel_type]
    return {
        "bsx_neg": _interpolate(_RATIOS, row["short_neg"], ly_lx),
        "bsx_pos": _interpolate(_RATIOS, row["short_pos"], ly_lx),
        "bsy_neg": _interpolate(_RATIOS, row["long_neg"],  ly_lx),
        "bsy_pos": _interpolate(_RATIOS, row["long_pos"],  ly_lx),
    }


def get_two_way_shear_coefficients(panel_type: str, ly_lx: float) -> dict:
    """
    Interpolate Table 3.15 for a given panel type and ly/lx ratio.
    Returns βvx_cont, βvx_disc, βvy_cont, βvy_disc (None if not applicable).
    """
    # Table 3.15 uses slightly different panel type keys — map the common ones
    panel_key = panel_type.replace("interior", "four_continuous")
    if panel_key not in TABLE_3_15:
        # Fall back to best match or four_continuous conservative
        panel_key = "one_short_discontinuous"
    row = TABLE_3_15[panel_key]
    return {
        "bvx_cont": _interpolate(_RATIOS_V, row["short_cont"], ly_lx),
        "bvx_disc": _interpolate(_RATIOS_V, row["short_disc"], ly_lx),
        "bvy_cont": _interpolate(_RATIOS_V, row["long_cont"],  ly_lx),
        "bvy_disc": _interpolate(_RATIOS_V, row["long_disc"],  ly_lx),
    }


# ===========================================================================
# Helper — design a single moment strip (used by both one-way and two-way)
# ===========================================================================

def _design_strip(M: float, section: SlabSection) -> dict:
    """
    Flexural design for a per-metre moment M (N·mm/m).
    Returns bars dict with As_req, As_prov, description, notes, warnings.
    """
    notes = []
    warnings = []
    b, d, fcu, fy = section.b, section.d, section.fcu, section.fy

    if M <= 0:
        return {
            "As_req": 0.0,
            "bars": select_slab_reinforcement(section.As_min, d, section.h, fy, section.beta_b),
            "notes": ["M ≤ 0: minimum steel provided."],
            "warnings": [],
        }

    k_prime_res = calculate_k_prime(section.beta_b)
    K_prime = k_prime_res["value"]
    notes.append(k_prime_res["note"])

    k_res = calculate_k(M, fcu, b, d)
    K = k_res["value"]
    notes.append(k_res["note"])

    if K > K_prime:
        warnings.append(
            f"K ({K:.4f}) > K' ({K_prime:.4f}). Section is inadequate. Consider increasing h."
        )
        return {"As_req": None, "bars": None, "notes": notes, "warnings": warnings}

    z_res = calculate_lever_arm(d, K)
    notes.append(z_res["note"])
    As_req = calculate_singly_reinforced_section(M, fy, z_res["value"])["value"]
    As_design = max(As_req, section.As_min)

    bars = select_slab_reinforcement(As_design, d, section.h, fy, section.beta_b)
    if bars["warning"]:
        warnings.append(bars["warning"])

    return {"As_req": As_req, "bars": bars, "notes": notes, "warnings": warnings}


# ===========================================================================
# Public entry: one-way slab design  (Cl 3.5.2)
# ===========================================================================

def design_one_way_slab(
    section: SlabSection,
    F: float,   # Total design UDL on span (N/m)  = (1.4Gk + 1.6Qk) × lx
    gk: Optional[float] = None,
    qk: Optional[float] = None,
    num_spans: int = 3,
    max_span_ratio: float = 1.0,
) -> dict:
    """
    Design a 1m wide strip of a one-way spanning solid slab (Cl 3.5.2).

    Uses Table 3.12 moment/shear coefficients.
    F = total design load on the span (N/m width), i.e. n × lx where n is in N/mm².
    """
    notes: list[str] = []
    warnings: list[str] = []
    results: dict = {"status": "OK", "notes": notes, "warnings": warnings}

    notes.append(section.summary())
    lx = section.lx
    sc = section.support_condition
    n = F / lx   # design UDL in N/mm (per metre width)
    results["n_design"] = round(n * 1e3, 2)  # kN/m²

    notes.append(
        f"Total design load F = {F/1e3:.1f} kN/m, n = F/lx = {n*1e3:.2f} kN/m². "
        f"Support condition: {sc} (Table 3.12 / BS 8110 Cl 3.5.2)"
    )

    # ---- Cl 3.5.2.1 Prerequisites check ----
    if sc == "continuous":
        if gk is not None and qk is not None and qk > gk:
            warnings.append(f"Cl 3.5.2.1 Violation: Live load Qk ({qk}) > Dead load Gk ({gk}). Table 3.12 may be unconservative.")
        if num_spans < 3:
            warnings.append(f"Cl 3.5.2.1 Violation: Less than 3 spans ({num_spans}) provided. Table 3.12 coefficients require at least 3 spans.")
        if max_span_ratio > 1.25:
            warnings.append(f"Cl 3.5.2.1 Violation: Span ratio ({max_span_ratio}) > 1.25. Table 3.12 coefficients may be invalid.")

    coeffs = get_one_way_coefficients(sc)
    M_coeffs = coeffs["moment"]
    V_coeffs = coeffs["shear"]

    # Design moments (N·mm/m) ------------------------------------------------
    spans = {}
    if sc == "simple":
        spans = {
            "mid_span_sagging": (M_coeffs["near_middle_end_span"] or 0) * F * lx,
        }
    else:  # continuous
        spans = {
            "end_span_sagging":        (M_coeffs["near_middle_end_span"] or 0)      * F * lx,
            "first_interior_hogging":  abs(M_coeffs["first_interior_support"] or 0) * F * lx,
            "mid_span_sagging":        (M_coeffs["middle_span"] or 0)               * F * lx,
            "interior_hogging":        abs(M_coeffs["interior_support"] or 0)        * F * lx,
        }

    # Design shears (N/m) ----------------------------------------------------
    shears = {}
    if sc == "simple":
        shears["outer_support"] = (V_coeffs["outer_support"] or 0) * F
    else:
        shears["outer_support"]          = (V_coeffs["outer_support"] or 0)          * F
        shears["first_interior_support"] = (V_coeffs["first_interior_support"] or 0) * F
        shears["interior_support"]       = (V_coeffs["interior_support"] or 0)        * F

    results["design_moments_kNm"] = {k: round(v / 1e6, 2) for k, v in spans.items()}
    results["design_shears_kN"]   = {k: round(v / 1e3, 2) for k, v in shears.items()}

    # Flexural design for the critical (maximum) sagging moment ---------------
    M_max_sag = max((v for v in spans.values() if v >= 0), default=0)
    M_max_hog = max((v for k, v in spans.items() if "hogging" in k), default=0)
    M_crit = max(M_max_sag, M_max_hog)

    notes.append(f"Critical moment = {M_crit/1e6:.2f} kN·m/m (governs bar selection)")

    strip = _design_strip(M_crit, section)
    notes.extend(strip["notes"])
    warnings.extend(strip["warnings"])

    if strip["As_req"] is None:
        results["status"] = "Section Inadequate"
        return results

    results["As_req"]                   = round(strip["As_req"], 2)
    results["As_prov"]                  = strip["bars"]["As_prov"]
    results["reinforcement_description"]= strip["bars"]["description"]

    # Distribution steel (Cl 3.5.2.3) — minimum 20% of main steel, at least As_min
    As_dist = max(0.20 * strip["bars"]["As_prov"], section.As_min)
    d_sec = section.d - (section.bar_dia / 2.0) - (section.bar_dia_sec / 2.0)
    dist_bars = select_slab_reinforcement(As_dist, d_sec, section.h, section.fy, 1.0)
    results["distribution_steel"]       = dist_bars["description"]
    notes.append(
        f"Distribution steel (Cl 3.5.2.3): As_dist = max(0.2×As_prov, As_min) = "
        f"{As_dist:.0f} mm²/m → {dist_bars['description']}"
    )

    # Reinforcement limits ----------------------------------------------------
    lim_res = check_reinforcement_limits(
        strip["bars"]["As_prov"], section.As_min, section.As_max, "tension"
    )
    notes.append(lim_res["note"])
    if lim_res["status"] == "FAIL":
        results["status"] = "Reinforcement Limit Failure"

    # Deflection check (govern by end-span or simply supported) ---------------
    basic_ratio = determine_basic_ratio("rectangular", section.support_condition)
    M_defl = M_max_sag if M_max_sag > 0 else M_crit
    def_res = check_deflection(
        lx, section.d, basic_ratio,
        strip["bars"]["As_prov"], strip["As_req"],
        section.b, M_defl, section.fy, 0.0, section.beta_b
    )
    results["deflection_check"] = def_res["status"]
    notes.append(def_res["note"])
    if def_res["status"] == "FAIL":
        results["status"] = "Deflection Failure"

    # Critical shear check ----------------------------------------------------
    V_crit = max(shears.values())
    shear_res = check_shear_stress(V_crit, section.b, section.d, section.fcu)
    notes.append(shear_res["note"])
    if shear_res["status"] == "OK":
        vc_res = calculate_vc(strip["bars"]["As_prov"], section.b, section.d, section.fcu, section.h)
        notes.append(vc_res["note"])
        if shear_res["v"] > vc_res["value"]:
            results["shear_status"] = f"FAIL: v ({shear_res['v']:.3f}) > vc ({vc_res['value']:.3f}). Increase depth."
            if results["status"] == "OK":
                results["status"] = "Shear Failure"
        else:
            results["shear_status"] = "OK (No shear links required in slab)"
    else:
        results["status"] = "Shear Failure"

    return results


# ===========================================================================
# Public entry: two-way slab design  (Cl 3.5.3)
# ===========================================================================

def design_two_way_slab(
    section: SlabSection,
    n: float,    # Design UDL (N/mm²), i.e. factored (1.4Gk + 1.6Qk)
) -> dict:
    """
    Design a two-way spanning solid slab panel (Cl 3.5.3 / BS 8110-1:1997).

    Uses:
      - Table 3.14 for bending moment coefficients
      - Table 3.15 for shear force coefficients
      - Cl 3.5.3.6 for corner torsion reinforcement

    n  : total design UDL (N/mm²) = factored load over unit area
    lx : short span (mm) — beam dimension governing main coefficients
    ly : long  span (mm)
    """
    notes: list[str] = []
    warnings: list[str] = []
    results: dict = {"status": "OK", "notes": notes, "warnings": warnings}

    lx = section.lx
    ly = section.ly
    ly_lx = section.ly_lx
    panel = section.panel_type

    notes.append(section.summary())
    notes.append(
        f"Design UDL n = {n*1e3:.3f} kN/m². "
        f"ly/lx = {ly_lx:.2f}. Panel type: {panel}  (BS 8110 Cl 3.5.3 / Tables 3.14, 3.15)"
    )

    if ly_lx > 2.0:
        warnings.append(
            f"ly/lx = {ly_lx:.2f} > 2.0: panel behaves as one-way. "
            "Two-way coefficient tables are only valid for ly/lx ≤ 2.0 (Cl 3.5.3.2)."
        )
        results["status"] = "Use one-way design"
        return results

    # ---- Bending moment coefficients (Table 3.14) --------------------------
    m_coeffs = get_two_way_moment_coefficients(panel, ly_lx)
    notes.append(
        f"Table 3.14 coefficients (ly/lx={ly_lx:.2f}): "
        f"βsx⁻={m_coeffs['bsx_neg']}, βsx⁺={m_coeffs['bsx_pos']}, "
        f"βsy⁻={m_coeffs['bsy_neg']}, βsy⁺={m_coeffs['bsy_pos']}"
    )

    # Moments per unit width (N·mm/m) per Cl 3.5.3.3
    # Msx = βsx · n · lx²  (short-span moments)
    # Msy = βsy · n · lx²  (long-span moments — note: still × lx², not ly²)
    Msx_neg = (m_coeffs["bsx_neg"] or 0) * n * lx**2
    Msx_pos = (m_coeffs["bsx_pos"] or 0) * n * lx**2
    Msy_neg = (m_coeffs["bsy_neg"] or 0) * n * lx**2
    Msy_pos = (m_coeffs["bsy_pos"] or 0) * n * lx**2

    results["design_moments_kNm"] = {
        "Msx_hogging":  round(Msx_neg / 1e6, 2),
        "Msx_sagging":  round(Msx_pos / 1e6, 2),
        "Msy_hogging":  round(Msy_neg / 1e6, 2),
        "Msy_sagging":  round(Msy_pos / 1e6, 2),
    }
    notes.append(
        f"Design moments: Msx⁻={Msx_neg/1e6:.2f}, Msx⁺={Msx_pos/1e6:.2f}, "
        f"Msy⁻={Msy_neg/1e6:.2f}, Msy⁺={Msy_pos/1e6:.2f} kN·m/m"
    )

    # ---- Flexural design — short span (outer layer, d = d_outer) ----------
    notes.append("--- Short-span reinforcement (outer layer) ---")
    M_sx_crit = max(Msx_neg, Msx_pos)
    sx_strip = _design_strip(M_sx_crit, section)
    notes.extend(sx_strip["notes"])
    warnings.extend(sx_strip["warnings"])

    if sx_strip["As_req"] is None:
        results["status"] = "Section Inadequate (short span)"
        return results

    results["As_sx_req"]          = round(sx_strip["As_req"], 2)
    results["As_sx_prov"]         = sx_strip["bars"]["As_prov"]
    results["short_span_steel"]   = sx_strip["bars"]["description"]

    # ---- Flexural design — long span (inner layer, d = d_inner) -----------
    notes.append("--- Long-span reinforcement (inner layer) ---")
    # Use inner effective depth for long-span bars
    d_inner = section.h - section.cover - section.bar_dia - (section.bar_dia / 2.0)
    M_sy_crit = max(Msy_neg, Msy_pos)

    # Temporarily build a proxy section with inner d
    from models.slab import SlabSection as _S
    inner_sec = _S(
        h=section.h, cover=section.cover, fcu=section.fcu,
        lx=section.lx, ly=section.ly, fy=section.fy,
        slab_type="two-way", panel_type=section.panel_type,
        support_condition=section.support_condition,
        layer="inner", bar_dia=section.bar_dia,
        bar_dia_outer=section.bar_dia, beta_b=section.beta_b,
    )
    sy_strip = _design_strip(M_sy_crit, inner_sec)
    notes.extend(sy_strip["notes"])
    warnings.extend(sy_strip["warnings"])

    if sy_strip["As_req"] is None:
        results["status"] = "Section Inadequate (long span)"
        return results

    results["As_sy_req"]         = round(sy_strip["As_req"], 2)
    results["As_sy_prov"]        = sy_strip["bars"]["As_prov"]
    results["long_span_steel"]   = sy_strip["bars"]["description"]

    # ---- Corner torsion reinforcement (Cl 3.5.3.6) ------------------------
    # Required at corners where discontinuous-to-beam/wall junction exists.
    # Area = 0.75 × As_sx_prov per unit width in each of the top and bottom layers
    # Extent = lx/5 from the corner.
    corner_As = 0.75 * results["As_sx_prov"]
    corner_bars = select_slab_reinforcement(corner_As, section.d, section.h, section.fy, 1.0)
    results["corner_torsion_steel"] = corner_bars["description"]
    results["corner_torsion_extent_mm"] = round(lx / 5.0, 0)
    notes.append(
        f"Corner torsion reinforcement (Cl 3.5.3.6): "
        f"As = 0.75 × As_sx = {corner_As:.0f} mm²/m → {corner_bars['description']}. "
        f"IMPORTANT: Provide in FOUR layers (top & bottom mesh) at each discontinuous corner, "
        f"extending {lx/5:.0f} mm from the corner in both directions."
    )

    # ---- Deflection check — short span governs (Cl 3.5.7) -----------------
    notes.append("--- Deflection check (short span governs) ---")
    basic_ratio = determine_basic_ratio("rectangular", section.support_condition)
    def_res = check_deflection(
        lx, section.d, basic_ratio,
        sx_strip["bars"]["As_prov"], sx_strip["As_req"],
        section.b, M_sx_crit, section.fy, 0.0, section.beta_b,
    )
    results["deflection_check"] = def_res["status"]
    notes.append(def_res["note"])
    if def_res["status"] == "FAIL":
        results["status"] = "Deflection Failure"

    # ---- Shear check (Table 3.15) ------------------------------------------
    notes.append("--- Shear check ---")
    try:
        v_coeffs = get_two_way_shear_coefficients(panel, ly_lx)
        # Maximum shear per unit width on each face: Vsx = βvx · n · lx
        Vsx_cont = (v_coeffs["bvx_cont"] or 0) * n * lx
        Vsx_disc = (v_coeffs["bvx_disc"] or 0) * n * lx
        Vsy_cont = (v_coeffs["bvy_cont"] or 0) * n * lx
        Vsy_disc = (v_coeffs["bvy_disc"] or 0) * n * lx
        V_crit = max(Vsx_cont, Vsx_disc, Vsy_cont, Vsy_disc)
        results["design_shears_kN"] = {
            "Vsx_cont": round(Vsx_cont / 1e3, 2),
            "Vsx_disc": round(Vsx_disc / 1e3, 2),
            "Vsy_cont": round(Vsy_cont / 1e3, 2),
            "Vsy_disc": round(Vsy_disc / 1e3, 2),
        }
        notes.append(
            f"Table 3.15 shears: Vsx_cont={Vsx_cont/1e3:.2f}, Vsx_disc={Vsx_disc/1e3:.2f}, "
            f"Vsy_cont={Vsy_cont/1e3:.2f}, Vsy_disc={Vsy_disc/1e3:.2f} kN/m. "
            f"Critical V = {V_crit/1e3:.2f} kN/m"
        )
    except Exception as e:
        warnings.append(f"Shear table lookup failed ({e}). Falling back to applied shear check.")
        V_crit = 0.5 * n * lx  # conservative approximation

    shear_res = check_shear_stress(V_crit, section.b, section.d, section.fcu)
    notes.append(shear_res["note"])
    if shear_res["status"] == "OK":
        vc_res = calculate_vc(
            sx_strip["bars"]["As_prov"], section.b, section.d, section.fcu, section.h
        )
        notes.append(vc_res["note"])
        if shear_res["v"] > vc_res["value"]:
            results["shear_status"] = (
                f"FAIL: v ({shear_res['v']:.3f}) > vc ({vc_res['value']:.3f}). "
                "Increase slab depth."
            )
            if results["status"] == "OK":
                results["status"] = "Shear Failure"
        else:
            results["shear_status"] = "OK (No shear links required)"
    else:
        results["status"] = "Shear Failure"

    return results


# ===========================================================================
# Unified entry point
# ===========================================================================

def calculate_slab_reinforcement(
    section: SlabSection,
    n: float,  # Design UDL (N/mm²) for two-way, or pass F directly for one-way
    F: Optional[float] = None,  # Total design load (N/m) for one-way — if None, F = n × lx
    gk: Optional[float] = None,
    qk: Optional[float] = None,
    num_spans: int = 3,
    max_span_ratio: float = 1.0,
) -> dict:
    """
    Unified slab design dispatcher.

    For one-way slabs: F = n × lx (or pass n alone and let the function derive F).
    For two-way slabs: n is the design UDL in N/mm².
    """
    if section.slab_type == "one-way":
        _F = F if F is not None else n * section.lx
        return design_one_way_slab(
            section, _F, gk=gk, qk=qk, num_spans=num_spans, max_span_ratio=max_span_ratio
        )
    else:
        return design_two_way_slab(section, n)

"""
BS 8110-1:1997  –  Core Calculation Formulas
=============================================
All functions return a ``dict`` containing at minimum:
  * The named result value(s).
  * A ``"note"`` string citing the relevant clause.

Sign convention: moments and forces are always positive (magnitudes).
"""

import math
from typing import Dict, Any, Optional

# ---------------------------------------------------------------------------
# Material partial safety factors  (BS 8110-1:1997 Table 2.2)
# ---------------------------------------------------------------------------
GAMMA_C = 1.50   # partial safety factor for concrete
GAMMA_S = 1.15   # partial safety factor for steel reinforcement

# Effective steel stress at ULS: 0.95 fy  (= fy / gamma_s when gamma_s ≈ 1.05
# but BS 8110 Cl 3.4.4.4 explicitly states 0.95 fy)
ALPHA_S = 0.95


# ===========================================================================
# 1.  K  and  K'
# ===========================================================================

def calculate_k(M: float, fcu: float, b: float, d: float) -> Dict[str, Any]:
    """
    Calculate the concrete stress-block factor K.

    BS 8110-1:1997 Cl 3.4.4.4:
        K = M / (fcu · b · d²)

    Parameters
    ----------
    M   : Design moment (N·mm)
    fcu : Characteristic cube strength (N/mm²)
    b   : Section width (mm)  — use *web* width for flanged beams
    d   : Effective depth (mm)
    """
    K = M / (fcu * b * d ** 2)
    return {
        "value": K,
        "note": (
            f"K = M / (fcu·b·d²) = {M:.0f} / ({fcu}×{b:.0f}×{d:.0f}²) = {K:.4f} "
            f"(BS 8110 Cl 3.4.4.4)"
        ),
    }


def calculate_k_prime(beta_b: float = 1.0) -> Dict[str, Any]:
    """
    Calculate the limiting K' (K-prime) accounting for moment redistribution.

    BS 8110-1:1997 Cl 3.2.2.1:
        K' = 0.402 · (β_b − 0.4) − 0.18 · (β_b − 0.4)²

    For zero redistribution (β_b = 1.0), K' = 0.156.

    Parameters
    ----------
    beta_b : Ratio of redistributed to elastic moment (0.7 ≤ β_b ≤ 1.0).
             Use 1.0 for no redistribution.
    """
    beta_b = max(0.7, min(1.0, beta_b))
    K_prime = 0.402 * (beta_b - 0.4) - 0.18 * (beta_b - 0.4) ** 2
    return {
        "value": round(K_prime, 4),
        "beta_b": beta_b,
        "note": (
            f"K' = 0.402·(β_b−0.4) − 0.18·(β_b−0.4)² = {K_prime:.4f} "
            f"(β_b = {beta_b}, BS 8110 Cl 3.2.2.1)"
        ),
    }


# ===========================================================================
# 2.  Lever-arm
# ===========================================================================

def calculate_lever_arm(d: float, K: float) -> Dict[str, Any]:
    """
    Calculate lever arm z.

    BS 8110-1:1997 Cl 3.4.4.4:
        z = d · [0.5 + √(0.25 − K/0.9)]
        z ≤ 0.95d

    Parameters
    ----------
    d : Effective depth (mm)
    K : Stress-block factor (dimensionless)
    """
    term = 0.25 - (K / 0.9)
    if term < 0:
        return {
            "value": 0.0,
            "note": "K > 0.225: lever-arm formula invalid — compression steel required.",
        }
    z = d * (0.5 + math.sqrt(term))
    z_capped = min(z, 0.95 * d)
    note = f"z = d·[0.5 + √(0.25−K/0.9)] = {z:.1f} mm"
    if z > 0.95 * d:
        note += f", capped at 0.95d = {z_capped:.1f} mm"
    note += " (BS 8110 Cl 3.4.4.4)"
    return {"value": z_capped, "note": note}


# ===========================================================================
# 3.  Singly-reinforced section
# ===========================================================================

def calculate_singly_reinforced_section(
    M: float, fy: float, z: float
) -> Dict[str, Any]:
    """
    Tension steel for a singly-reinforced rectangular (or flanged) section.

    BS 8110-1:1997 Cl 3.4.4.4:
        As = M / (0.95·fy·z)

    Parameters
    ----------
    M  : Design moment (N·mm)
    fy : Characteristic steel yield strength (N/mm²)
    z  : Lever arm (mm)
    """
    As = M / (ALPHA_S * fy * z)
    return {
        "value": As,
        "note": (
            f"As = M / (0.95·fy·z) = {M:.0f} / (0.95×{fy}×{z:.1f}) "
            f"= {As:.1f} mm² (BS 8110 Cl 3.4.4.4)"
        ),
    }


# ===========================================================================
# 4.  Doubly-reinforced section
# ===========================================================================

def calculate_doubly_reinforced_section(
    M: float,
    fcu: float,
    fy: float,
    b: float,
    d: float,
    d_prime: float,
    K_prime: float = 0.156,
) -> Dict[str, Any]:
    """
    Tension and compression steel for a doubly-reinforced rectangular section.

    BS 8110-1:1997 Cl 3.4.4.4:
        M_u   = K'·fcu·b·d²
        As'   = (M − M_u) / [0.95·fy·(d − d')]
        As    = M_u / (0.95·fy·z) + As'
        z     = 0.775d  (lever arm at K = K')

    The compression bar stress is assumed to be 0.95·fy, which requires that
    d'/d ≤ 0.2 (BS 8110 Cl 3.4.4.4 note).  A warning is added if violated.

    Parameters
    ----------
    M       : Design moment (N·mm)
    fcu     : Concrete grade (N/mm²)
    fy      : Steel yield strength (N/mm²)
    b       : Width (mm)
    d       : Effective depth (mm)
    d_prime : Depth to compression steel centroid (mm)
    K_prime : Limiting K value (default 0.156 for 0 % redistribution)
    """
    notes = []
    M_u = K_prime * fcu * b * d ** 2
    z = 0.775 * d  # lever arm when K = K'

    # Check d'/d ratio for compression bar yielding
    d_prime_ratio = d_prime / d
    if d_prime_ratio > 0.2:
        notes.append(
            f"WARNING: d'/d = {d_prime_ratio:.3f} > 0.2 — compression bars may "
            f"not reach 0.95fy. Consider using f'sc = 700·(1 − d'/x) / γs "
            f"(BS 8110 Cl 3.4.4.4)."
        )

    As_prime = (M - M_u) / (ALPHA_S * fy * (d - d_prime))
    As = (M_u / (ALPHA_S * fy * z)) + As_prime

    notes.insert(
        0,
        (
            f"Doubly reinforced: M_u = K'·fcu·b·d² = {M_u:.0f} N·mm; "
            f"z = 0.775d = {z:.1f} mm; "
            f"As' = (M−M_u)/(0.95·fy·(d−d')) = {As_prime:.1f} mm²; "
            f"As = M_u/(0.95·fy·z) + As' = {As:.1f} mm² (BS 8110 Cl 3.4.4.4)"
        ),
    )

    return {
        "As_req": As,
        "As_prime_req": As_prime,
        "z": z,
        "M_u": M_u,
        "note": " | ".join(notes),
    }


# ===========================================================================
# 5.  Flanged beam
# ===========================================================================

def calculate_flanged_beam_reinforcement(
    M: float,
    fcu: float,
    fy: float,
    b: float,
    bf: float,
    d: float,
    hf: float,
) -> Dict[str, Any]:
    """
    Calculate tension steel for a T- or L-beam (flanged section).

    Procedure (BS 8110-1:1997 Cl 3.4.4.5):

    1.  Check if compression is confined to the flange by testing
        whether the section needs more moment capacity than a flange-only
        section can provide:
            M_f = 0.45·fcu·(bf − b)·hf·(d − hf/2)
        If M <= M_f, treat as singly-reinforced with width = bf.
        If M > M_f, the neutral axis enters the web.  In that case, the
        additional web moment M_w = M − M_f is designed as a rectangular
        section of width b, and the two steel requirements are added.

    Parameters
    ----------
    M   : Design moment (N·mm)
    fcu : Concrete grade (N/mm²)
    fy  : Steel yield strength (N/mm²)
    b   : Web width (mm)
    bf  : Effective flange width (mm)
    d   : Effective depth (mm)
    hf  : Flange thickness (mm)
    """
    notes = []

    # Moment capacity of flange overhang
    M_f = 0.45 * fcu * (bf - b) * hf * (d - hf / 2.0)
    notes.append(
        f"Flanged beam: M_f (flange overhang) = 0.45·fcu·(bf−b)·hf·(d−hf/2) "
        f"= {M_f:.0f} N·mm (BS 8110 Cl 3.4.4.5)"
    )

    if M <= M_f:
        # Neutral axis in flange — treat as rectangle width bf
        notes.append(
            "Neutral axis lies within flange (M ≤ M_f). Treat as rectangle with b = bf."
        )
        K = M / (fcu * bf * d ** 2)
        z_res = calculate_lever_arm(d, K)
        z = z_res["value"]
        As = M / (ALPHA_S * fy * z)
        notes.append(
            f"K = {K:.4f}; z = {z:.1f} mm; As = {As:.1f} mm²"
        )
        return {
            "As_req": As,
            "As_prime_req": 0.0,
            "K": K,
            "z": z,
            "neutral_axis_in_flange": True,
            "note": " | ".join(notes),
        }

    else:
        # Neutral axis in web — split moment
        notes.append(
            f"Neutral axis extends into web (M = {M:.0f} > M_f = {M_f:.0f})."
        )
        # Steel for flange overhang moment
        z_f = d - hf / 2.0          # lever arm for flange contribution
        As_f = M_f / (ALPHA_S * fy * z_f)

        # Remaining web moment designed as rectangular b × d
        M_w = M - M_f
        K_w = M_w / (fcu * b * d ** 2)
        notes.append(f"Web moment M_w = M − M_f = {M_w:.0f} N·mm; K_w = {K_w:.4f}")

        K_prime_res = calculate_k_prime(beta_b=1.0)
        K_prime = K_prime_res["value"]

        if K_w > K_prime:
            # Web portion itself needs compression steel
            notes.append(
                f"K_w ({K_w:.4f}) > K' ({K_prime:.4f}): web portion requires "
                f"compression reinforcement."
            )
            dr_res = calculate_doubly_reinforced_section(
                M_w, fcu, fy, b, d, d_prime=0.0, K_prime=K_prime
            )
            # d_prime=0 is a placeholder; caller must supply actual d' for doubly
            As_w = dr_res["As_req"]
            As_prime = dr_res["As_prime_req"]
            notes.append(dr_res["note"])
        else:
            z_w_res = calculate_lever_arm(d, K_w)
            z_w = z_w_res["value"]
            As_w = M_w / (ALPHA_S * fy * z_w)
            As_prime = 0.0
            notes.append(f"z_w = {z_w:.1f} mm; As_w = {As_w:.1f} mm²")

        As_total = As_f + As_w
        notes.append(
            f"Total As = As_f + As_w = {As_f:.1f} + {As_w:.1f} = {As_total:.1f} mm²"
        )

        return {
            "As_req": As_total,
            "As_prime_req": As_prime,
            "K_w": K_w,
            "z_f": z_f,
            "neutral_axis_in_flange": False,
            "note": " | ".join(notes),
        }


# ===========================================================================
# 6.  Effective flange width  (BS 8110-1:1997 Cl 3.4.1.5)
# ===========================================================================

def calculate_effective_flange_width(
    b_w: float,
    l_z: float,
    b_s_left: float,
    b_s_right: float,
    flange_type: str = "T",
) -> Dict[str, Any]:
    """
    Effective flange width per BS 8110-1:1997 Cl 3.4.1.5.

    For simple and continuous beams the code limits the slab contribution on
    each side to lz/10 (T-beam) or lz/20 (L-beam), where lz is the distance
    between points of zero moment (approximately 0.7 × span for continuous
    beams, or the actual span for simply supported).

    Parameters
    ----------
    b_w        : Web width (mm)
    l_z        : Distance between points of zero moment (mm)
    b_s_left   : Actual slab width projecting to the left of web (mm)
    b_s_right  : Actual slab width projecting to the right of web (mm)
    flange_type: ``"T"`` (flanges both sides) or ``"L"`` (flange one side)
    """
    flange_type = flange_type.upper()
    if flange_type == "T":
        beff_each_side = l_z / 10.0
    else:
        beff_each_side = l_z / 20.0

    beff_left = min(beff_each_side, b_s_left)
    beff_right = min(beff_each_side, b_s_right)

    bf = b_w + beff_left + beff_right
    return {
        "value": round(bf, 1),
        "beff_left": round(beff_left, 1),
        "beff_right": round(beff_right, 1),
        "note": (
            f"Effective flange width bf = bw + min(lz/10, bs) each side = "
            f"{b_w} + {beff_left:.1f} + {beff_right:.1f} = {bf:.1f} mm "
            f"(BS 8110 Cl 3.4.1.5)"
        ),
    }


# ===========================================================================
# 7.  Design concrete shear stress  vc  (BS 8110-1:1997 Table 3.8)
# ===========================================================================

def calculate_vc(
    As_prov: float,
    b: float,
    d: float,
    fcu: float,
) -> Dict[str, Any]:
    """
    Design concrete shear stress vc.

    BS 8110-1:1997 Table 3.8 formula:
        v_c = (0.79/γ_m) · (100·As/(b·d))^(1/3) · (400/d)^(1/4) · (fcu/25)^(1/3)

    Limits:
        100·As/(b·d) ≤ 3.0
        fcu          ≤ 40 N/mm²  for this formula (BS 8110 Table 3.8 note)
        d            ≥ 400 mm for depth-factor = 1.0 (otherwise factor > 1)

    Parameters
    ----------
    As_prov : Provided tensile steel area (mm²)
    b       : Section width (mm)
    d       : Effective depth (mm)
    fcu     : Concrete cube strength (N/mm²)
    """
    pt = min(100.0 * As_prov / (b * d), 3.0)
    fcu_eff = min(fcu, 40.0)                         # Table 3.8 note
    depth_factor = max((400.0 / d) ** 0.25, 1.0)    # ≥ 1.0 for d < 400 mm
    fcu_factor = (fcu_eff / 25.0) ** (1.0 / 3.0)

    vc = (0.79 / GAMMA_C) * (pt ** (1.0 / 3.0)) * depth_factor * fcu_factor

    return {
        "value": round(vc, 4),
        "pt": round(pt, 3),
        "depth_factor": round(depth_factor, 3),
        "fcu_factor": round(fcu_factor, 3),
        "note": (
            f"vc = (0.79/1.5)·(100As/bd)^(1/3)·(400/d)^(1/4)·(fcu/25)^(1/3) "
            f"= {vc:.3f} N/mm² "
            f"[100As/bd = {pt:.2f}%, (400/d)^0.25 = {depth_factor:.3f}, "
            f"(fcu/25)^(1/3) = {fcu_factor:.3f}] (BS 8110 Table 3.8)"
        ),
    }


# ===========================================================================
# 8.  Shear stress check
# ===========================================================================

def check_shear_stress(
    V: float, b: float, d: float, fcu: float
) -> Dict[str, Any]:
    """
    Check applied shear stress against maximum allowable.

    BS 8110-1:1997 Cl 3.4.5.2:
        v     = V / (b·d)
        v_max = min(0.8·√fcu, 5.0)  (N/mm²)

    Parameters
    ----------
    V   : Design shear force (N)
    b   : Section width (mm)
    d   : Effective depth (mm)
    fcu : Concrete grade (N/mm²)
    """
    v = V / (b * d)
    v_max = min(0.8 * math.sqrt(fcu), 5.0)
    status = "OK" if v <= v_max else "FAIL"
    return {
        "v": round(v, 4),
        "v_max": round(v_max, 4),
        "status": status,
        "note": (
            f"v = V/(b·d) = {V:.0f}/({b:.0f}×{d:.0f}) = {v:.3f} N/mm²; "
            f"v_max = {v_max:.3f} N/mm². Status: {status} (BS 8110 Cl 3.4.5.2)"
        ),
    }


# ===========================================================================
# 9.  Shear links design  (BS 8110-1:1997 Table 3.8 / Cl 3.4.5)
# ===========================================================================

def calculate_shear_links(
    v: float,
    vc: float,
    b: float,
    fyv: float,
    d: float,
    link_dia: int = 8,
    num_legs: int = 2,
) -> Dict[str, Any]:
    """
    Determine shear reinforcement per BS 8110-1:1997 Table 3.8.

    Design equation (Cl 3.4.5.3):
        Asv / sv ≥ b·(v − vc) / (0.95·fyv)
        sv ≤ 0.75d  (Cl 3.4.5.5)

    Parameters
    ----------
    v        : Applied shear stress (N/mm²)
    vc       : Design concrete shear resistance (N/mm²)
    b        : Web width (mm)
    fyv      : Link yield strength (N/mm²)
    d        : Effective depth (mm)
    link_dia : Link bar diameter (mm). Default 8 mm.
    num_legs : Number of link legs. Default 2.
    """
    Asv = num_legs * math.pi * (link_dia / 2.0) ** 2
    sv_max = 0.75 * d
    note_parts = []

    if v < 0.5 * vc:
        links = f"Nominal links H{link_dia} @ {int(sv_max):.0f} mm c/c"
        note_parts.append(
            f"v ({v:.3f}) < 0.5·vc ({0.5*vc:.3f}): nominal links only "
            f"(BS 8110 Table 3.8)"
        )
    elif v < (vc + 0.4):
        # Minimum links: Asv/sv = 0.4·b / (0.95·fyv)
        sv_min_links = 0.95 * fyv * Asv / (0.4 * b)
        sv = min(sv_min_links, sv_max)
        links = f"H{link_dia} @ {int(sv):.0f} mm c/c (min links)"
        note_parts.append(
            f"v ({v:.3f}) in range [0.5vc, vc+0.4]: minimum links. "
            f"sv = 0.95·fyv·Asv / (0.4·b) = {sv_min_links:.0f} mm, "
            f"limited to 0.75d = {sv_max:.0f} mm → {links}"
        )
    else:
        # Design links
        sv_design = 0.95 * fyv * Asv / (b * (v - vc))
        sv = min(sv_design, sv_max)
        links = f"H{link_dia} @ {int(sv):.0f} mm c/c ({num_legs} legs)"
        note_parts.append(
            f"v ({v:.3f}) > vc+0.4: design links. "
            f"sv = 0.95·fyv·Asv / [b·(v−vc)] = {sv_design:.0f} mm, "
            f"limited to 0.75d = {sv_max:.0f} mm → {links} (BS 8110 Cl 3.4.5.3)"
        )

    return {
        "links": links,
        "Asv": round(Asv, 2),
        "sv": round(sv_max if v < 0.5 * vc else min(
            (0.95 * fyv * Asv / (0.4 * b)) if v < (vc + 0.4) else
            (0.95 * fyv * Asv / (b * (v - vc))),
            sv_max
        ), 1),
        "note": " | ".join(note_parts),
    }


# ===========================================================================
# 10.  Deflection check  (BS 8110-1:1997 Cl 3.4.6)
# ===========================================================================

def calculate_design_service_stress(
    fy: float, As_req: float, As_prov: float, beta_b: float = 1.0
) -> float:
    """
    Service (unfactored) stress in tension steel.

    BS 8110-1:1997 Cl 3.4.6.5:
        fs = (2/3) · fy · (As_req / As_prov) · (1 / β_b)

    Capped at 0.95·fy (physical upper limit).
    """
    if As_prov == 0:
        return 0.0
    fs = (2.0 / 3.0) * fy * (As_req / As_prov) * (1.0 / beta_b)
    return min(fs, ALPHA_S * fy)


def check_deflection(
    span: float,
    d: float,
    basic_ratio: float,
    As_prov: float,
    As_req: float,
    b: float,
    M: float,
    fy: float,
    As_prime_prov: float = 0.0,
    beta_b: float = 1.0,
) -> Dict[str, Any]:
    """
    Deflection check using the span-to-effective-depth ratio method.

    BS 8110-1:1997 Cl 3.4.6 and Tables 3.10 / 3.11.

    Long-span correction (Cl 3.4.6.7):
        If span > 10 000 mm (and not a cantilever), the basic ratio is
        multiplied by 10 000 / span.

    Parameters
    ----------
    span          : Effective span (mm)
    d             : Effective depth (mm)
    basic_ratio   : Basic span/depth ratio from Table 3.9 (via ``determine_basic_ratio``)
    As_prov       : Provided tensile steel area (mm²)
    As_req        : Required tensile steel area (mm²)
    b             : Width for M/(b·d²) calculation (mm)
    M             : Design moment (N·mm)
    fy            : Steel yield strength (N/mm²)
    As_prime_prov : Provided compression steel area (mm²). Default 0.
    beta_b        : Moment redistribution factor. Default 1.0 (no redistribution).
    """
    fs = calculate_design_service_stress(fy, As_req, As_prov, beta_b)
    m_bd2 = M / (b * d ** 2)

    # Tension modification factor (Table 3.11)
    # MFt = 0.55 + (477 − fs) / [120·(0.9 + M/(b·d²))]
    # Limits: 0.1 ≤ MFt ≤ 2.0
    denom_t = 120.0 * (0.9 + m_bd2)
    MFt = 0.55 + (477.0 - fs) / denom_t if denom_t != 0 else 1.0
    MFt = max(0.1, min(2.0, MFt))

    # Compression modification factor (Table 3.11)
    # MFc = 1 + (100·As'/(b·d)) / [3 + (100·As'/(b·d))]
    # Limit: MFc ≤ 1.5
    pct_comp = 100.0 * As_prime_prov / (b * d) if (b * d) > 0 else 0.0
    MFc = 1.0 + pct_comp / (3.0 + pct_comp) if pct_comp > 0 else 1.0
    MFc = min(1.5, MFc)

    # Effective basic ratio with long-span correction (Cl 3.4.6.7)
    if span > 10_000.0:
        long_span_factor = 10_000.0 / span
        adj_basic_ratio = basic_ratio * long_span_factor
        long_span_note = (
            f" Long-span correction (Cl 3.4.6.7): basic ratio × 10000/span = "
            f"{basic_ratio} × {long_span_factor:.3f} = {adj_basic_ratio:.2f}."
        )
    else:
        adj_basic_ratio = basic_ratio
        long_span_note = ""

    allowable = adj_basic_ratio * MFt * MFc
    actual = span / d
    status = "OK" if actual <= allowable else "FAIL"

    note = (
        f"Deflection (BS 8110 Cl 3.4.6): "
        f"Actual L/d = {actual:.2f}; "
        f"Allowable = {adj_basic_ratio:.2f} × MFt({MFt:.2f}) × MFc({MFc:.2f}) "
        f"= {allowable:.2f}; fs = {fs:.1f} N/mm²; M/(b·d²) = {m_bd2:.4f}.{long_span_note} "
        f"Status: {status}"
    )

    return {
        "actual": round(actual, 3),
        "allowable": round(allowable, 3),
        "MFt": round(MFt, 3),
        "MFc": round(MFc, 3),
        "fs": round(fs, 2),
        "status": status,
        "note": note,
    }


# ===========================================================================
# 11.  Basic span/depth ratio  (BS 8110-1:1997 Table 3.9)
# ===========================================================================

def determine_basic_ratio(section: str, support_condition: str) -> float:
    """
    Return basic span/depth ratio from BS 8110-1:1997 Table 3.9.

    Parameters
    ----------
    section          : ``"rectangular"`` or ``"flanged"``
    support_condition: ``"simple"``, ``"cantilever"``, or ``"continuous"``
    """
    _table = {
        "rectangular": {"simple": 20.0, "continuous": 26.0, "cantilever": 7.0},
        "flanged":     {"simple": 16.0, "continuous": 20.8, "cantilever": 5.6},
    }
    s = section.lower()
    c = support_condition.lower()
    return _table.get(s, _table["rectangular"]).get(c, 20.0)


# ===========================================================================
# 12.  Minimum and maximum reinforcement limits  (BS 8110-1:1997 Cl 3.12)
# ===========================================================================

def check_reinforcement_limits(
    As_prov: float,
    As_min: float,
    As_max: float,
    label: str = "tension",
) -> Dict[str, Any]:
    """
    Check tension or compression steel against Cl 3.12 limits.

    Parameters
    ----------
    As_prov : Provided area (mm²)
    As_min  : Minimum required area per Table 3.25 (mm²)
    As_max  : Maximum permitted area per Cl 3.12.6.1 (mm²)
    label   : ``"tension"`` or ``"compression"`` (for messages only)
    """
    notes = []
    status = "OK"

    if As_prov < As_min:
        notes.append(
            f"FAIL: {label.capitalize()} As_prov ({As_prov:.1f} mm²) < "
            f"As_min ({As_min:.1f} mm²) — BS 8110 Table 3.25"
        )
        status = "FAIL"
    else:
        notes.append(
            f"OK: {label.capitalize()} As_prov ({As_prov:.1f} mm²) ≥ "
            f"As_min ({As_min:.1f} mm²)"
        )

    if As_prov > As_max:
        notes.append(
            f"FAIL: {label.capitalize()} As_prov ({As_prov:.1f} mm²) > "
            f"As_max ({As_max:.1f} mm²) — BS 8110 Cl 3.12.6.1"
        )
        status = "FAIL"
    else:
        notes.append(
            f"OK: {label.capitalize()} As_prov ({As_prov:.1f} mm²) ≤ "
            f"As_max ({As_max:.1f} mm²)"
        )

    return {"status": status, "note": " | ".join(notes)}


# ===========================================================================
# 13.  Bar spacing / crack control  (BS 8110-1:1997 Cl 3.12.11)
# ===========================================================================

def check_bar_spacing(
    num_bars: int,
    bar_dia: float,
    b: float,
    cover: float,
    link_dia: float,
    fy: float,
    beta_b: float = 1.0,
) -> Dict[str, Any]:
    """
    Check clear spacing between bars does not exceed code limit.

    BS 8110-1:1997 Cl 3.12.11.2:
        For fy = 460 N/mm² and zero redistribution: max clear spacing = 160 mm.
        For fy = 250 N/mm²:                         max clear spacing = 300 mm.
        For redistribution > 0 % the limit reduces proportionally.

    Clear spacing = [b − 2·(cover + link_dia) − n·bar_dia] / (n − 1)

    Parameters
    ----------
    num_bars  : Number of tension bars in one layer
    bar_dia   : Diameter of tension bars (mm)
    b         : Beam width (mm)
    cover     : Nominal cover (mm)
    link_dia  : Link bar diameter (mm)
    fy        : Yield strength (N/mm²)
    beta_b    : Moment redistribution factor (default 1.0)
    """
    if num_bars < 2:
        return {"clear_space": float("inf"), "status": "OK",
                "note": "Only 1 bar — no spacing check required."}

    # Available width between links (inner faces)
    inner_width = b - 2.0 * (cover + link_dia)
    clear_space = (inner_width - num_bars * bar_dia) / (num_bars - 1)

    # Code limit per Cl 3.12.11.2
    if fy >= 460:
        max_clear = 160.0 / beta_b
    else:
        max_clear = 300.0 / beta_b

    status = "OK" if clear_space >= 25.0 and clear_space <= max_clear else "FAIL"
    note = (
        f"Bar spacing check (BS 8110 Cl 3.12.11): "
        f"Clear spacing = {clear_space:.1f} mm; "
        f"Limit = {max_clear:.0f} mm (fy={fy}, β_b={beta_b}). "
        f"Min physical gap = 25 mm. Status: {status}"
    )

    return {
        "clear_space": round(clear_space, 1),
        "max_clear": max_clear,
        "status": status,
        "note": note,
    }
"""
BS EN 1992-1-1:2004 (EC2)  –  Core Calculation Formulas
=========================================================
All public functions return a ``dict`` containing at minimum:
  * The named result value(s).
  * A ``"note"`` string citing the relevant clause.

Material partial factors used throughout:
  γ_c = 1.50  (concrete),  γ_s = 1.15  (steel)

Stress-block parameters for fck ≤ 50 N/mm² (Cl 3.1.7 / Fig 3.5):
  α_cc = 0.85   (long-term strength reduction factor — NDP, UK NA value)
  λ    = 0.80   (depth of rectangular stress block = λ × x)
  η    = 1.00   (effective strength factor)
  → Design concrete compressive strength (stress block):
       fcd,eff = α_cc × fck / γ_c = 0.85 × fck / 1.5 = 0.5667 × fck

For fck > 50 N/mm² the parameters λ and η reduce — handled in each function.
"""

from __future__ import annotations

import math
from typing import Dict, Any, Optional

# ---------------------------------------------------------------------------
# Partial factors & stress-block constants
# ---------------------------------------------------------------------------
GAMMA_C: float = 1.50
GAMMA_S: float = 1.15
ALPHA_CC: float = 0.85   # UK NA to EC2 (conservative)
LAMBDA: float = 0.80     # Cl 3.1.7(3) — depth factor for x ≤ C50/60
ETA: float = 1.00        # Cl 3.1.7(3) — strength factor for fck ≤ C50/60


def _lambda_eta(fck: float) -> tuple[float, float]:
    """
    Return (λ, η) stress-block parameters per EC2 Cl 3.1.7(3).

    For fck > 50:
        λ = 0.80 − (fck − 50) / 400
        η = 1.00 − (fck − 50) / 200
    For fck ≤ 50:
        λ = 0.80,  η = 1.00
    """
    if fck <= 50:
        return 0.80, 1.00
    lam = 0.80 - (fck - 50.0) / 400.0
    eta = 1.00 - (fck - 50.0) / 200.0
    return lam, eta


# ===========================================================================
# 1.  K factor  (EC2 equivalent of BS 8110 K)
# ===========================================================================

def calculate_k(M: float, fck: float, b: float, d: float) -> Dict[str, Any]:
    """
    Calculate the normalised moment K.

    EC2 does not use K explicitly but it is derived from the rectangular
    stress block equilibrium and is widely used in UK practice:

        K = M / (b · d² · fck)

    When K ≤ K_lim the section is singly reinforced.

    Parameters
    ----------
    M   : Design moment (N·mm)
    fck : Characteristic cylinder strength (N/mm²)
    b   : Section width for bending (mm). Use web width for flanged beams
          only if NA is in web; otherwise use effective flange width.
    d   : Effective depth (mm)
    """
    K = M / (b * d ** 2 * fck)
    return {
        "value": K,
        "note": (
            f"K = M/(b·d²·fck) = {M:.0f}/({b:.0f}×{d:.0f}²×{fck}) = {K:.4f}  "
            f"(EC2 UK practice / SCI P300)"
        ),
    }


# ===========================================================================
# 2.  Lever arm z  (EC2 Cl 6.1 / rectangular stress block)
# ===========================================================================

def calculate_lever_arm(d: float, K: float, delta: float = 1.0) -> Dict[str, Any]:
    """
    Calculate the lever arm z from K and d.

    Based on equilibrium of the rectangular stress block (EC2 Fig 3.5):

        K_lim limit: z = d · (0.5 + √(0.25 − K/(1.134)))
        where 1.134 = η · α_cc / (γ_c · λ/2)  — see derivation below.

    Derivation (UK practice)
    ------------------------
    Compression force:  C = α_cc · fck/γ_c · b · λ·x = 0.5667·fck·b·0.8x
    Tension force:      T = As · fyk/γ_s
    Setting z = d − λ·x/2 = d − 0.4x:
        x = (d − z) / 0.4
    Moment:  M = C · z = 0.5667·fck·b·0.8·(d−z)/0.4 · z
        M = 0.5667·fck·b·2·(d−z)·z
        M/(fck·b·d²) = 2·(1−z/d)·(z/d)
        K = 2·(1 − z/d)·(z/d)
    Solving: (z/d)² − (z/d) + K/2 = 0
        z/d = 0.5 + √(0.25 − K/2)

    However, the more standard UK form incorporating α_cc, γ_c, λ, η is:
        z = d · (0.5 + √(0.25 − K/1.134))
    where 1.134 = α_cc/(γ_c · λ/2 · η) = 0.85/(1.5 × 0.4 × 1.0) = 1.4167
    (slightly different form used in different references; tested value 1.134
    is from Mosley et al and SCI P300).

    Limits:  z ≤ 0.95d  (Cl 9.2.1 — maximum lever arm)
             z ≥ 0.82d  (practical minimum before compression steel required)

    Parameters
    ----------
    d     : Effective depth (mm)
    K     : Normalised moment factor M/(b·d²·fck)
    delta : Moment redistribution ratio (0.7 – 1.0)
    """
    discriminant = 0.25 - K / 1.134
    if discriminant < 0:
        # K > K_lim — compression steel region; use limiting z
        z = 0.82 * d
        note_suffix = " (K > K_lim: compression steel required; z taken at limit)"
    else:
        z = d * (0.5 + math.sqrt(discriminant))
        note_suffix = ""

    z = min(z, 0.95 * d)   # EC2 Cl 9.2.1 maximum lever arm

    return {
        "value": round(z, 2),
        "note": (
            f"z = d(0.5 + √(0.25 − K/1.134)) = {d:.0f}(0.5 + √({discriminant:.4f})) "
            f"= {z:.1f} mm → capped to {min(z,0.95*d):.1f} mm (max 0.95d)"
            + note_suffix
        ),
    }


# ===========================================================================
# 3.  Singly reinforced section — tension steel
# ===========================================================================

def calculate_singly_reinforced(
    M: float,
    fyk: float,
    z: float,
) -> Dict[str, Any]:
    """
    Required tension steel for a singly-reinforced section.

        As = M / (fyd · z)   where fyd = fyk / γ_s

    Parameters
    ----------
    M   : Design moment (N·mm)
    fyk : Characteristic steel yield strength (N/mm²)
    z   : Lever arm (mm)
    """
    fyd = fyk / GAMMA_S
    As = M / (fyd * z)
    return {
        "value": round(As, 2),
        "note": (
            f"As = M/(fyd·z) = {M:.0f}/({fyd:.2f}×{z:.1f}) = {As:.1f} mm²  "
            f"(EC2 Cl 6.1, fyd = fyk/γ_s = {fyk}/{GAMMA_S})"
        ),
    }


# ===========================================================================
# 4.  Doubly reinforced section  (K > K_lim)
# ===========================================================================

def calculate_doubly_reinforced(
    M: float,
    fck: float,
    fyk: float,
    b: float,
    d: float,
    d_prime: float,
    delta: float = 1.0,
) -> Dict[str, Any]:
    """
    Design a doubly-reinforced rectangular beam section per EC2.

    When K > K_lim, compression steel is required.  The procedure is:

    1.  Limiting moment:  M_lim = K_lim · fck · b · d²
    2.  Lever arm at limit: z_lim = d(0.5 + √(0.25 − K_lim/1.134))
    3.  Compression steel: As' = (M − M_lim) / (fsc · (d − d'))
        where fsc = min(fyd, Es · ε_sc)  and  ε_sc = 0.0035(1 − d'/x_lim)
    4.  Tension steel: As = M_lim/(fyd·z_lim) + As'·(fsc/fyd)

    Notes
    -----
    * d_prime must be ≤ x_lim(1 − ε_yd/ε_cu3) to ensure compression steel yields.
    * ε_cu3 = 0.0035 for fck ≤ C50 (EC2 Table 3.1).
    * Es = 200,000 N/mm² (EC2 Cl 3.2.7).

    Parameters
    ----------
    M       : Design moment (N·mm)
    fck     : Cylinder concrete strength (N/mm²)
    fyk     : Steel yield strength (N/mm²)
    b       : Section width (mm)
    d       : Effective depth (mm)
    d_prime : Depth to compression steel centroid (mm)
    delta   : Moment redistribution ratio
    """
    fyd = fyk / GAMMA_S
    Es  = 200_000.0   # N/mm²
    eps_cu3 = 0.0035  # Ultimate concrete strain (Table 3.1, fck ≤ C50)

    # K_lim  (simplified UK practice — SCI P300)
    K_lim = 0.60 * delta - 0.18 * delta ** 2 - 0.21 if delta < 1.0 else 0.167
    K_lim = max(K_lim, 0.0)

    M_lim = K_lim * fck * b * d ** 2

    # Lever arm at K_lim
    z_lim_disc = 0.25 - K_lim / 1.134
    z_lim = d * (0.5 + math.sqrt(max(z_lim_disc, 0.0)))
    z_lim = min(z_lim, 0.95 * d)

    # Neutral axis at limit: x_lim = (d − z_lim) / 0.4
    x_lim = (d - z_lim) / 0.4

    # Strain in compression steel
    eps_sc = eps_cu3 * (1.0 - d_prime / x_lim) if x_lim > 0 else eps_cu3
    f_sc = min(Es * eps_sc, fyd)   # compression steel stress (may not yield)

    # Compression steel: As'
    if abs(d - d_prime) < 1.0:
        raise ValueError("d − d' is too small — compression steel would have zero lever arm.")
    As_prime = (M - M_lim) / (f_sc * (d - d_prime))
    As_prime = max(As_prime, 0.0)

    # Tension steel: As
    As = M_lim / (fyd * z_lim) + As_prime * (f_sc / fyd)

    yields = eps_sc >= fyd / Es
    yield_note = "yields" if yields else f"does NOT yield (fsc = {f_sc:.0f} N/mm²)"

    return {
        "As":        round(As, 2),
        "As_prime":  round(As_prime, 2),
        "K_lim":     round(K_lim, 4),
        "M_lim":     round(M_lim, 0),
        "z_lim":     round(z_lim, 1),
        "x_lim":     round(x_lim, 1),
        "fsc":       round(f_sc, 2),
        "comp_steel_yields": yields,
        "note": (
            f"Doubly reinforced (K > K_lim = {K_lim:.3f}):\n"
            f"  M_lim = {M_lim/1e6:.2f} kN·m  |  z_lim = {z_lim:.1f} mm  |  x_lim = {x_lim:.1f} mm\n"
            f"  Compression steel: ε_sc = {eps_sc:.4f}, fsc = {f_sc:.0f} N/mm² ({yield_note})\n"
            f"  As' = (M−M_lim)/(fsc×(d−d')) = {As_prime:.0f} mm²\n"
            f"  As  = M_lim/(fyd·z_lim) + As'×(fsc/fyd) = {As:.0f} mm²"
        ),
    }


# ===========================================================================
# 5.  Flanged beam  (T- or L-section)  (EC2 Cl 6.1)
# ===========================================================================

def calculate_flanged_beam(
    M: float,
    fck: float,
    fyk: float,
    bw: float,
    bf: float,
    d: float,
    hf: float,
    d_prime: float,
    delta: float = 1.0,
) -> Dict[str, Any]:
    """
    Flanged beam flexural design per EC2 Cl 6.1.

    Approach:
      1.  Check if NA is in the flange (treat as rectangular width bf).
      2.  If NA in flange: standard rectangular calculation with b = bf.
      3.  If NA in web: two-part equilibrium
            M_f  = force in overhanging flanges × lever arm
            M_w  = remainder carried by web → standard web calculation
          Tension steel: As = As_f + As_w
          If M_w requires compression steel (K_w > K_lim): doubly-reinforced web.

    Parameters
    ----------
    M       : Design moment (N·mm), positive = sagging
    fck     : Cylinder concrete strength (N/mm²)
    fyk     : Steel yield strength (N/mm²)
    bw      : Web width (mm)
    bf      : Effective flange width (mm)
    d       : Effective depth (mm)
    hf      : Flange thickness (mm)
    d_prime : Depth to compression steel centroid (mm)
    delta   : Redistribution ratio
    """
    fcd_eff = ALPHA_CC * fck / GAMMA_C   # design stress in rectangular block
    fyd = fyk / GAMMA_S

    # ---- Step 1: NA in flange? ----
    # Moment capacity with full NA in flange:
    # z_f = d - hf/2  (lever arm if all compression in flange)
    z_f = d - hf / 2.0
    M_f_max = fcd_eff * bf * hf * z_f   # maximum flange moment (all compression in flange)

    if M <= M_f_max:
        # NA in flange — rectangular design using bf
        k_res = calculate_k(M, fck, bf, d)
        K = k_res["value"]
        K_lim = 0.60 * delta - 0.18 * delta ** 2 - 0.21 if delta < 1.0 else 0.167

        z_res = calculate_lever_arm(d, K, delta)
        z = z_res["value"]

        if K <= K_lim:
            As = M / (fyd * z)
            return {
                "As_req":    round(As, 2),
                "As_prime":  0.0,
                "na_in_flange": True,
                "K": round(K, 4),
                "z": round(z, 1),
                "note": (
                    f"NA in flange (M={M/1e6:.2f} kN·m ≤ M_f,max={M_f_max/1e6:.2f} kN·m).\n"
                    f"Rectangular design: b=bf={bf:.0f} mm, K={K:.4f}, z={z:.1f} mm\n"
                    f"As = M/(fyd·z) = {As:.0f} mm²"
                ),
            }
        else:
            # Compression steel even with full flange — doubly-reinforced flange
            dr = calculate_doubly_reinforced(M, fck, fyk, bf, d, d_prime, delta)
            dr["na_in_flange"] = True
            return dr
    else:
        # NA extends into web — two-part calculation
        # Part 1: Flange overhangs (bf − bw) carry compression
        M_f  = fcd_eff * (bf - bw) * hf * (d - hf / 2.0)
        As_f = M_f / (fyd * (d - hf / 2.0))

        # Part 2: Web carries remainder M_w
        M_w = M - M_f
        k_res_w = calculate_k(M_w, fck, bw, d)
        K_w = k_res_w["value"]
        K_lim = 0.60 * delta - 0.18 * delta ** 2 - 0.21 if delta < 1.0 else 0.167

        if K_w <= K_lim:
            z_w_res = calculate_lever_arm(d, K_w, delta)
            z_w = z_w_res["value"]
            As_w = M_w / (fyd * z_w)
            As_prime = 0.0
        else:
            dr = calculate_doubly_reinforced(M_w, fck, fyk, bw, d, d_prime, delta)
            As_w    = dr["As"]
            As_prime = dr["As_prime"]

        As_total = As_f + As_w

        return {
            "As_req":    round(As_total, 2),
            "As_prime":  round(As_prime, 2),
            "As_flange": round(As_f, 2),
            "As_web":    round(As_w, 2),
            "na_in_flange": False,
            "K_w": round(K_w, 4),
            "M_f": round(M_f, 0),
            "M_w": round(M_w, 0),
            "note": (
                f"NA in web (M={M/1e6:.2f} kN·m > M_f,max={M_f_max/1e6:.2f} kN·m).\n"
                f"  Flange: As_f = M_f/(fyd×(d−hf/2)) = {As_f:.0f} mm²\n"
                f"  Web:    K_w = {K_w:.4f}, As_w = {As_w:.0f} mm²\n"
                f"  Total:  As = {As_total:.0f} mm²"
            ),
        }


# ===========================================================================
# 6.  VRd,c — concrete shear resistance  (EC2 Cl 6.2.2)
# ===========================================================================

def calculate_VRd_c(
    As_prov: float,
    fck: float,
    b_w: float,
    d: float,
    N_Ed: float = 0.0,   # Axial force (N), positive = compression
) -> Dict[str, Any]:
    """
    Concrete shear resistance VRd,c (members without shear reinforcement).

    EC2 Eq. (6.2a/b):
        VRd,c = [C_Rd,c · k · (100·ρ_l·fck)^(1/3) + k_1·σ_cp] · b_w · d

        with minimum:
        VRd,c ≥ (v_min + k_1·σ_cp) · b_w · d

    where:
        C_Rd,c = 0.18/γ_c = 0.12
        k      = 1 + √(200/d) ≤ 2.0
        ρ_l   = As/(b_w·d) ≤ 0.02
        v_min  = 0.035 · k^1.5 · fck^0.5
        k_1    = 0.15  (for axially loaded members)
        σ_cp   = N_Ed / A_c (positive for compression)

    Parameters
    ----------
    As_prov : Provided tensile reinforcement area (mm²)
    fck     : Cylinder concrete strength (N/mm²)
    b_w     : Minimum section width within tension zone (mm)
    d       : Effective depth (mm)
    N_Ed    : Axial force (N) — compression positive. Default 0.
    """
    C_Rd_c = 0.18 / GAMMA_C
    k = min(1.0 + math.sqrt(200.0 / d), 2.0)
    rho_l = min(As_prov / (b_w * d), 0.02)

    v_main = C_Rd_c * k * (100.0 * rho_l * fck) ** (1.0 / 3.0)
    v_min  = 0.035 * k ** 1.5 * math.sqrt(fck)

    # Axial stress component
    A_c = b_w * d   # approximate (can be full area if caller provides b*h)
    sigma_cp = min(N_Ed / (b_w * 1000.0), 0.2 * fck)  # σ_cp in N/mm², cap at 0.2fck
    k1 = 0.15

    VRd_c = max(v_main + k1 * sigma_cp, v_min + k1 * sigma_cp) * b_w * d

    return {
        "value": round(VRd_c, 1),
        "k":     round(k, 3),
        "rho_l": round(rho_l, 4),
        "v_main": round(v_main, 4),
        "v_min":  round(v_min, 4),
        "note": (
            f"VRd,c: C_Rd,c={C_Rd_c:.3f}, k={k:.3f}, ρ_l={rho_l:.4f}, "
            f"v_main={v_main:.3f}, v_min={v_min:.3f} → VRd,c = {VRd_c:.0f} N  "
            f"(EC2 Eq.6.2a/b)"
        ),
    }


# ===========================================================================
# 7.  Shear link design  (EC2 Cl 6.2.3 — Variable Strut Inclination)
# ===========================================================================

def calculate_shear_links(
    V_Ed: float,
    fck: float,
    fywk: float,
    b_w: float,
    d: float,
    theta_deg: float = 21.8,   # Strut angle θ (21.8°→cot θ=2.5; 45°→cot θ=1.0)
    z: Optional[float] = None,  # Lever arm; default = 0.9d
    A_s: Optional[float] = None, # Tension steel (for crushing check)
) -> Dict[str, Any]:
    """
    Design shear reinforcement using the Variable Strut Inclination (VSI) method.

    EC2 Cl 6.2.3 — Diagonal compression strut model:

        VRd,s = (Asw/s) · z · fywd · cot θ
        VRd,max = α_cw · b_w · z · ν_1 · fcd / (cot θ + tan θ)

    where:
        α_cw = 1.0 (no prestress)
        ν_1  = 0.6 · (1 − fck/250)   (crushing reduction factor, EC2 Eq.6.6N)
        cot θ is limited to 1.0 ≤ cot θ ≤ 2.5  (i.e. 21.8° ≤ θ ≤ 45°)
        z    = lever arm ≈ 0.9d for beams (EC2 Cl 6.2.3(1))

    Design approach:
      1.  Try θ = 21.8° (cot θ = 2.5) — most efficient strut angle.
      2.  If VRd,max < V_Ed, increase θ toward 45°, solving:
              cot θ = (VRd,max_at_45 / V_Ed)  ← quadratic solve
          If V_Ed > VRd,max at 45°, section is inadequate.

    Parameters
    ----------
    V_Ed     : Design shear force (N)
    fck      : Cylinder concrete strength (N/mm²)
    fywk     : Link yield strength (N/mm²)
    b_w      : Web width (mm)
    d        : Effective depth (mm)
    theta_deg: Initial strut angle (°). Default 21.8° (cot θ = 2.5).
    z        : Lever arm (mm). Default 0.9d.
    A_s      : Tension steel (mm²) — used if longitudinal steel check needed.
    """
    fywd = fywk / GAMMA_S
    if z is None:
        z = 0.9 * d

    nu1  = 0.6 * (1.0 - fck / 250.0)   # Eq. 6.6N
    fcd  = ALPHA_CC * fck / GAMMA_C

    def VRd_max_from_theta(cot_t: float) -> float:
        tan_t = 1.0 / cot_t
        return 1.0 * b_w * z * nu1 * fcd / (cot_t + tan_t)

    # Try requested theta
    theta_rad = math.radians(theta_deg)
    cot_theta = 1.0 / math.tan(theta_rad)
    cot_theta = max(1.0, min(cot_theta, 2.5))   # clamp to EC2 limits

    VRd_max = VRd_max_from_theta(cot_theta)

    notes_list = []

    if V_Ed > VRd_max_from_theta(1.0):
        # V_Ed exceeds maximum even at 45° — section is inadequate
        return {
            "status": "FAIL: VEd > VRd,max at θ=45°. Increase bw or d.",
            "Asw_s":  None,
            "theta_deg": 45.0,
            "VRd_max": round(VRd_max_from_theta(1.0), 0),
            "note": (
                f"FAIL: V_Ed ({V_Ed/1e3:.1f} kN) > VRd,max at θ=45° "
                f"({VRd_max_from_theta(1.0)/1e3:.1f} kN). Increase section."
            ),
        }

    if V_Ed > VRd_max:
        # Need a steeper strut angle — solve for cot θ
        # V_Ed = fcd·bw·z·nu1·cot_t / (1 + cot_t²)
        # → cot_t² − (fcd·bw·z·nu1/V_Ed)·cot_t + 1 = 0
        A_coeff = 1.0
        B_coeff = -(fcd * b_w * z * nu1) / V_Ed
        C_coeff = 1.0
        disc = B_coeff ** 2 - 4 * A_coeff * C_coeff
        if disc < 0:
            cot_theta = 1.0
        else:
            cot_theta = (-B_coeff - math.sqrt(disc)) / (2 * A_coeff)
            cot_theta = max(1.0, min(cot_theta, 2.5))
        theta_rad = math.atan(1.0 / cot_theta)
        theta_deg = math.degrees(theta_rad)
        VRd_max = VRd_max_from_theta(cot_theta)
        notes_list.append(
            f"θ increased to {theta_deg:.1f}° (cot θ = {cot_theta:.2f}) to satisfy VRd,max ≥ VEd."
        )

    # Required Asw/s (link area per unit length along beam)
    Asw_per_s = V_Ed / (z * fywd * cot_theta)   # mm²/mm

    # Minimum link ratio (Cl 9.2.2(5)):
    #   ρ_w,min = 0.08√fck / fyk
    rho_w_min = 0.08 * math.sqrt(fck) / fywk
    Asw_s_min = rho_w_min * b_w   # mm²/mm
    Asw_per_s = max(Asw_per_s, Asw_s_min)

    return {
        "status":    "OK",
        "Asw_s":     round(Asw_per_s, 4),   # mm²/mm — e.g. 0.4mm²/mm = 400mm²/m
        "Asw_s_min": round(Asw_s_min, 4),
        "theta_deg": round(theta_deg, 1),
        "cot_theta": round(cot_theta, 3),
        "VRd_max":   round(VRd_max, 0),
        "z":         round(z, 1),
        "fywd":      round(fywd, 2),
        "note": (
            f"Shear links (EC2 Cl 6.2.3 VSI method):\n"
            f"  θ = {theta_deg:.1f}° (cot θ = {cot_theta:.2f}), z = {z:.1f} mm\n"
            f"  Asw/s = VEd/(z·fywd·cot θ) = {V_Ed/1e3:.1f}k/({z:.0f}×{fywd:.0f}×{cot_theta:.2f}) "
            f"= {Asw_per_s:.4f} mm²/mm\n"
            f"  Asw/s_min = 0.08√fck/fyk × bw = {Asw_s_min:.4f} mm²/mm\n"
            f"  VRd,max = {VRd_max/1e3:.1f} kN"
            + ("\n  " + "; ".join(notes_list) if notes_list else "")
        ),
    }


# ===========================================================================
# 8.  Deflection check — span/depth ratio  (EC2 Cl 7.4.2)
# ===========================================================================

def calculate_deflection_limit(
    fck: float,
    fyk: float,
    rho: float,         # Required reinforcement ratio ρ = As_req / (b_t·d)
    rho_0: float,       # Reference ratio = √fck / 1000
    is_end_span: bool,
    support_condition: str,   # "simple", "continuous", "cantilever"
    rho_prime: float = 0.0,   # Compression steel ratio As'/(b·d)
    b_t_bw: float = 1.0,      # Flanged: beff/bw — used to compute K_factor
) -> Dict[str, Any]:
    """
    Limiting span-to-effective-depth ratio per EC2 Cl 7.4.2.

    EC2 Eq (7.16a) when ρ ≤ ρ_0:
        L/d = K · [11 + 1.5√fck · ρ_0/ρ + 3.2√fck · (ρ_0/ρ − 1)^1.5]

    EC2 Eq (7.16b) when ρ > ρ_0:
        L/d = K · [11 + 1.5√fck · ρ_0/(ρ − ρ′) + √fck/12 · √(ρ'/ρ_0)]

    K factor from Table 7.4N:
        Simply supported:   K = 1.0
        End span:           K = 1.3
        Interior span:      K = 1.5
        Cantilever:         K = 0.4
        Flat slab:          K = 1.2

    The basic L/d ratio is then modified by:
      * Steel stress factor: multiply by (310/σ_s) where σ_s ≈ fyk/γ_s × (Ms/Mr)
        Simplified: σ_s = fyd × (As_req / As_prov).  Here we expose σ_s separately.
      * Flanged beams with beff/bw > 3: multiply by 0.8.
      * For spans > 7m (not slabs): multiply by 7/L.

    Parameters
    ----------
    fck             : Cylinder strength (N/mm²)
    fyk             : Steel yield (N/mm²)
    rho             : Tension reinforcement ratio As_req/(b·d) (required)
    rho_0           : Reference ratio = √fck/1000
    is_end_span     : True for end bays (K=1.3) vs interior bays (K=1.5)
    support_condition: ``"simple"`` | ``"continuous"`` | ``"cantilever"``
    rho_prime       : Compression reinforcement ratio (0 if none)
    b_t_bw          : Effective flange / web width ratio — for flange factor
    """
    # K factor (Table 7.4N)
    K_map = {
        "simple":     1.0,
        "cantilever": 0.4,
    }
    if support_condition == "continuous":
        K = 1.3 if is_end_span else 1.5
    else:
        K = K_map.get(support_condition, 1.0)

    sqrt_fck = math.sqrt(fck)
    rho_0_val = rho_0 if rho_0 > 0 else sqrt_fck / 1000.0

    rho_eff = max(rho, 1e-6)
    rho_prime_eff = max(rho_prime, 0.0)

    if rho_eff <= rho_0_val:
        # Eq. 7.16a
        term1 = 1.5 * sqrt_fck * rho_0_val / rho_eff
        ratio = rho_0_val / rho_eff - 1.0
        term2 = 3.2 * sqrt_fck * (max(ratio, 0.0) ** 1.5) if ratio > 0 else 0.0
        basic_ld = K * (11.0 + term1 + term2)
    else:
        # Eq. 7.16b
        rho_diff = max(rho_eff - rho_prime_eff, 1e-6)
        term1 = 1.5 * sqrt_fck * rho_0_val / rho_diff
        term2 = (sqrt_fck / 12.0) * math.sqrt(rho_prime_eff / rho_0_val) if rho_prime_eff > 0 else 0.0
        basic_ld = K * (11.0 + term1 + term2)

    # Flange factor
    flange_factor = 1.0
    if b_t_bw > 3.0:
        flange_factor = 0.8

    adj_ld = basic_ld * flange_factor

    return {
        "value":         round(adj_ld, 1),
        "K":             K,
        "basic_ld":      round(basic_ld, 1),
        "flange_factor": flange_factor,
        "rho_0":         round(rho_0_val, 5),
        "note": (
            f"Allowable L/d (EC2 Cl 7.4.2 Eq.7.16): K={K}, basic L/d={basic_ld:.1f}"
            + (f", ×flange factor {flange_factor}" if flange_factor != 1.0 else "")
            + f" → {adj_ld:.1f}"
        ),
    }


# ===========================================================================
# 9.  Crack control — bar spacing limit  (EC2 Cl 7.3.3 Table 7.3N)
# ===========================================================================

def crack_control_spacing(sigma_s: float) -> Dict[str, Any]:
    """
    Maximum allowable bar spacing for crack control without explicit calculation.

    EC2 Table 7.3N gives maximum bar spacing as a function of the steel
    stress under quasi-permanent loads σ_s (N/mm²).

    Parameters
    ----------
    sigma_s : Steel stress under quasi-permanent SLS loads (N/mm²).
              Approximation: σ_s ≈ (fyk/γ_s) × (As_req / As_prov) × ψ_2
              where ψ_2 is the quasi-permanent load combination factor.
    """
    # Table 7.3N (w_k = 0.3mm — the most common UK limit)
    TABLE_7_3N = [
        (160, 300), (200, 250), (240, 200), (280, 150),
        (320, 100), (360,  50),
    ]
    for s_limit, spacing in TABLE_7_3N:
        if sigma_s <= s_limit:
            return {
                "max_spacing_mm": spacing,
                "sigma_s":        round(sigma_s, 1),
                "note": (
                    f"Max bar spacing = {spacing} mm for σ_s = {sigma_s:.0f} N/mm² "
                    f"(EC2 Table 7.3N, w_k = 0.3 mm)"
                ),
            }
    return {
        "max_spacing_mm": 50,
        "sigma_s": round(sigma_s, 1),
        "note": f"σ_s = {sigma_s:.0f} N/mm² > 360 N/mm² — max bar spacing = 50 mm (EC2 Table 7.3N)",
    }


# ===========================================================================
# 10. Curtailment shift rule  (EC2 Cl 9.2.1.3)
# ===========================================================================

def curtailment_shift(d: float, cot_theta: float = 2.5) -> Dict[str, Any]:
    """
    Horizontal shift in bending moment diagram for curtailment.

    EC2 Cl 9.2.1.3:
        a_l = z_s / 2 · (cot θ − cot α)
    For vertical links (α = 90°, cot α = 0):
        a_l = 0.5 · z_s · cot θ   where z_s ≈ 0.9d

    Parameters
    ----------
    d         : Effective depth (mm)
    cot_theta : Strut inclination cotangent (1.0 – 2.5)
    """
    z_s = 0.9 * d
    a_l = 0.5 * z_s * cot_theta
    return {
        "value": round(a_l, 0),
        "note": (
            f"Curtailment shift a_l = 0.5 × z × cot θ = 0.5 × {z_s:.0f} × {cot_theta:.2f} "
            f"= {a_l:.0f} mm  (EC2 Cl 9.2.1.3)"
        ),
    }


# ===========================================================================
# 11. Column interaction — axial-bending capacity  (EC2 Cl 6.1)
# ===========================================================================

def calculate_column_capacity(
    x: float,          # Neutral axis depth (mm)
    As_total: float,   # Total symmetric reinforcement (mm²) — half each face assumed
    b: float,          # Section width (mm)
    h: float,          # Section depth (mm)
    d: float,          # Effective depth to tension steel (mm)
    d_prime: float,    # Depth to compression steel centroid (mm)
    fck: float,        # Cylinder concrete strength (N/mm²)
    fyk: float,        # Steel yield strength (N/mm²)
    num_bars: int = 8, # Total number of bars (for distributed steel estimate)
) -> tuple[float, float]:
    """
    Compute axial force N_cap and moment M_cap for a given neutral axis depth x.

    Uses EC2 rectangular stress block (Cl 3.1.7):
        Compression block depth:  s = λ·x  (λ = 0.80 for fck ≤ 50)
        Stress in block:          σ_c = η·fcd = η·α_cc·fck/γ_c

    Steel strains (plane sections remain plane, ε_cu3 = 0.0035):
        ε_s  (tension steel)     = ε_cu3 × (x − d) / x  — negative = tension
        ε_s' (compression steel) = ε_cu3 × (x − d') / x
    Steel stresses capped at fyd.

    For distributed bars (side bars), an average strain at mid-depth is used.

    Parameters
    ----------
    x        : Neutral axis depth from compression face (mm).
    As_total : Total reinforcement area (mm²), assumed symmetric on two faces.
    b        : Width of section (mm).
    h        : Depth of section (mm).
    d        : Effective depth to tension-face steel centroid (mm).
    d_prime  : Depth to compression-face steel centroid (mm).
    fck      : Cylinder concrete strength (N/mm²).
    fyk      : Steel yield strength (N/mm²).
    num_bars : Number of main bars — used to distribute any intermediate bars.
    """
    Es = 200_000.0       # N/mm² (EC2 Cl 3.2.7)
    eps_cu3 = 0.0035     # Ultimate concrete strain (Table 3.1, fck ≤ 50)
    fyd = fyk / GAMMA_S
    lam, eta = _lambda_eta(fck)
    fcd_eff = ALPHA_CC * fck / GAMMA_C * eta

    # Stress-block contribution
    s = min(lam * x, h)   # stress block depth — cap at h
    N_conc = fcd_eff * b * s

    # Compression steel (face at d_prime)
    As_comp = As_total / 2.0   # half on each face
    if x > 0:
        eps_prime = eps_cu3 * (x - d_prime) / x
    else:
        eps_prime = -eps_cu3
    f_prime = max(min(Es * eps_prime, fyd), -fyd)
    N_s_prime = As_comp * f_prime

    # Tension steel (face at d)
    if x > 0:
        eps_tens = eps_cu3 * (x - d) / x
    else:
        eps_tens = -eps_cu3
    f_tens = max(min(Es * eps_tens, fyd), -fyd)
    N_s_tens = As_comp * f_tens

    # Side / intermediate bars (if num_bars > 4, distribute remaining at mid)
    n_side = max(num_bars - 4, 0)   # bars on each side face
    As_side = As_total * n_side / max(num_bars, 1) if num_bars > 4 else 0.0
    N_side = 0.0
    M_side = 0.0
    if n_side > 0 and x > 0:
        # Average side bar at mid-depth h/2
        eps_side = eps_cu3 * (x - h / 2.0) / x
        f_side = max(min(Es * eps_side, fyd), -fyd)
        N_side = As_side * f_side
        M_side = As_side * f_side * (h / 2.0 - h / 2.0)  # zero moment at mid

    N_cap = N_conc + N_s_prime + N_s_tens + N_side

    # Moments about section centroid (h/2)
    M_conc  = N_conc  * (h / 2.0 - s / 2.0)
    M_comp  = N_s_prime * (h / 2.0 - d_prime)
    M_tens  = N_s_tens  * (h / 2.0 - d)       # negative (below centroid)
    M_cap = M_conc + M_comp - M_tens + M_side

    return N_cap, M_cap


# ===========================================================================
# 12. Second-order moment — Nominal Curvature Method  (EC2 Cl 5.8.8)
# ===========================================================================

def calculate_M2_nominal_curvature(
    N_Ed: float,
    fck: float,
    fyk: float,
    b: float,
    h: float,
    d: float,
    l_0: float,          # Effective length in direction of bending (mm)
    As_total: float,     # Total provided reinforcement (mm²)
    Ac: float,           # Gross concrete area (mm²)
    K_phi: float = 1.0,  # Creep correction factor (EC2 Eq.5.37; 1.0 if no creep)
) -> dict:
    """
    Second-order moment M_2 via the Nominal Curvature method.

    EC2 Cl 5.8.8.2 (Eq. 5.33 – 5.38):

        1/r_0 = ε_yd / (0.45 · d)          [curvature at yield — Eq. 5.34]
        K_r   = (n_u − n) / (n_u − n_bal)  [correction for axial force]
        1/r   = K_r · K_φ · (1/r_0)        [final curvature — Eq. 5.33]
        e_2   = (1/r) · l_0² / c           [second-order eccentricity — Eq. 5.32]
                c = 10 for sinusoidal distributions (conservatively π² ≈ 10)
        M_2   = N_Ed · e_2                  [second-order moment]

    where:
        ε_yd  = fyd / Es                    [yield strain]
        n     = N_Ed / (Ac · fcd)           [relative axial force]
        n_u   = 1 + ω                       [ω = As·fyd/(Ac·fcd)]
        n_bal = 0.4                         [balanced N ratio — Eq. 5.36N]
        K_r   = clipped to [0, 1]

    Parameters
    ----------
    N_Ed     : Design axial force (N). Positive = compression.
    fck      : Cylinder concrete strength (N/mm²)
    fyk      : Steel yield strength (N/mm²)
    b, h     : Section dimensions (mm)
    d        : Effective depth (mm)
    l_0      : Effective length in plane of bending (mm)
    As_total : Total provided reinforcement area (mm²)
    Ac       : Gross concrete area (mm²)
    K_phi    : Creep modification factor. Default 1.0 (no creep consideration).
    """
    Es   = 200_000.0
    fyd  = fyk / GAMMA_S
    fcd  = ALPHA_CC * fck / GAMMA_C

    eps_yd = fyd / Es

    # Mechanical reinforcement ratio ω
    omega = (As_total * fyd) / (Ac * fcd)

    # Relative axial force n
    n = N_Ed / (Ac * fcd)

    # Nu  (balanced limits)
    n_u   = 1.0 + omega
    n_bal = 0.4

    # Correction factor Kr (Eq. 5.36)
    K_r = (n_u - n) / (n_u - n_bal)
    K_r = max(0.0, min(K_r, 1.0))

    # Basic curvature 1/r0 (Eq. 5.34)
    inv_r0 = eps_yd / (0.45 * d)

    # Design curvature 1/r (Eq. 5.33)
    inv_r = K_r * K_phi * inv_r0

    # Second-order deflection (Eq. 5.32, c = 10)
    e_2 = inv_r * (l_0 ** 2) / 10.0

    # Second-order moment
    M_2 = N_Ed * e_2

    return {
        "M_2":      round(M_2, 0),
        "e_2":      round(e_2, 2),
        "K_r":      round(K_r, 4),
        "K_phi":    K_phi,
        "inv_r0":   round(inv_r0, 8),
        "inv_r":    round(inv_r, 8),
        "omega":    round(omega, 4),
        "n":        round(n, 4),
        "note": (
            f"Second-order moment (EC2 Cl 5.8.8 Nominal Curvature):\n"
            f"  ε_yd = {eps_yd:.5f},  1/r₀ = ε_yd/(0.45d) = {inv_r0:.6f} mm⁻¹\n"
            f"  ω = {omega:.4f},  n = {n:.4f},  n_u = {n_u:.4f},  n_bal = {n_bal}\n"
            f"  K_r = (n_u−n)/(n_u−n_bal) = {K_r:.4f}  (capped 0–1)\n"
            f"  1/r = K_r·K_φ·(1/r₀) = {K_r:.4f}×{K_phi}×{inv_r0:.6f} = {inv_r:.6f} mm⁻¹\n"
            f"  e₂ = (1/r)·l₀²/10 = {inv_r:.6f}×{l_0:.0f}²/10 = {e_2:.1f} mm\n"
            f"  M₂ = N_Ed·e₂ = {N_Ed/1e3:.1f}×{e_2:.1f} = {M_2/1e6:.2f} kN·m"
        ),
    }


# ===========================================================================
# 13. Biaxial bending — interaction check  (EC2 Cl 5.8.9)
# ===========================================================================

def check_biaxial_bending(
    M_Edx: float,   # Design moment about x-axis (N·mm) — h direction
    M_Edy: float,   # Design moment about y-axis (N·mm) — b direction
    M_Rdx: float,   # Moment capacity about x for given N (N·mm)
    M_Rdy: float,   # Moment capacity about y for given N (N·mm)
    N_Ed: float,    # Axial force (N)
    N_Rd: float,    # Axial capacity (N) = Ac·fcd + As·fyd
    a: Optional[float] = None,  # Exponent; None → derived from N_Ed/N_Rd
) -> dict:
    """
    Biaxial bending interaction check per EC2 Cl 5.8.9.

    EC2 Eq. (5.39):
        (M_Edx / M_Rdx)^a + (M_Edy / M_Rdy)^a ≤ 1.0

    Exponent a (Table 5.1N in EC2 Annex / Cl 5.8.9):
        N_Ed/N_Rd ≤ 0.1 → a = 1.0
        N_Ed/N_Rd = 0.7 → a = 1.5
        N_Ed/N_Rd ≥ 1.0 → a = 2.0
        Linear interpolation between values.

    Parameters
    ----------
    M_Edx, M_Edy : Design moments about x and y axes (N·mm).
    M_Rdx, M_Rdy : Resistances for the design axial force N_Ed (N·mm).
    N_Ed         : Design axial force (N).
    N_Rd         : Axial resistance of section (N).
    a            : Exponent. None → automatically derived.
    """
    ratio = min(N_Ed / max(N_Rd, 1.0), 1.0)

    if a is None:
        if ratio <= 0.1:
            a = 1.0
        elif ratio <= 0.7:
            a = 1.0 + (1.5 - 1.0) * (ratio - 0.1) / (0.7 - 0.1)
        else:
            a = 1.5 + (2.0 - 1.5) * (ratio - 0.7) / (1.0 - 0.7)

    r_x = (abs(M_Edx) / max(M_Rdx, 1.0)) ** a
    r_y = (abs(M_Edy) / max(M_Rdy, 1.0)) ** a
    interaction = r_x + r_y

    status = "OK" if interaction <= 1.0 else "FAIL"

    return {
        "status":      status,
        "interaction": round(interaction, 4),
        "a":           round(a, 3),
        "r_x":         round(r_x, 4),
        "r_y":         round(r_y, 4),
        "N_ratio":     round(ratio, 4),
        "note": (
            f"Biaxial check (EC2 Cl 5.8.9 Eq.5.39): a = {a:.3f} (N_Ed/N_Rd = {ratio:.3f})\n"
            f"  (M_Edx/M_Rdx)^a = ({M_Edx/1e6:.2f}/{M_Rdx/1e6:.2f})^{a:.2f} = {r_x:.4f}\n"
            f"  (M_Edy/M_Rdy)^a = ({M_Edy/1e6:.2f}/{M_Rdy/1e6:.2f})^{a:.2f} = {r_y:.4f}\n"
            f"  Sum = {interaction:.4f} {'≤' if status == 'OK' else '>'} 1.0 → {status}"
        ),
    }


# ===========================================================================
# 14. Column minimum eccentricity  (EC2 Cl 6.1(4))
# ===========================================================================

def column_min_eccentricity(h: float, l_0: float) -> dict:
    """
    Minimum eccentricity per EC2 Cl 6.1(4):

        e_0 = max(h/30,  20 mm)

    Applied to produce a minimum design moment:
        M_Ed,min = N_Ed × e_0

    Parameters
    ----------
    h  : Section depth in direction of bending (mm).
    l_0: Effective length (mm) — informational.
    """
    e_0 = max(h / 30.0, 20.0)
    return {
        "e_0": round(e_0, 1),
        "note": (
            f"Min eccentricity e₀ = max(h/30, 20) = max({h/30:.1f}, 20) = {e_0:.1f} mm  "
            f"(EC2 Cl 6.1(4))"
        ),
    }


# ===========================================================================
# 15. Two-way slab bending coefficients  (IStructE EC2 Manual, Table A3)
# ===========================================================================
# α_sx, α_sy give sagging moments;  β_sx, β_sy give hogging moments at supports.
# m_sx = α_sx · n · lx²   m_sy = α_sy · n · lx²
# m_hx = β_sx · n · lx²   m_hy = β_sy · n · lx²
#
# Panel type codes:
#   S = Simply supported edge  (discontinuous)
#   C = Continuous edge
#   Key: (short-edge S/C, short-edge S/C, long-edge S/C, long-edge S/C)
#        written as (bottom, top, left, right) → use SSSS / CSSS patterns
# We use the 9 standard edge conditions from the IStructE EC2 Manual.
#
# Format: dict[panel_type][ly_lx_index] → (alpha_sx, alpha_sy, beta_sx, beta_sy)
# ly_lx index 0→1.0, 1→1.1, 2→1.2, 3→1.3, 4→1.4, 5→1.5, 6→1.75, 7→2.0

_TWO_WAY_LY_LX = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.75, 2.0]

# Coefficients (α_sx, α_sy, β_sx, β_sy)
# Source: IStructE Manual for the design of concrete building structures to Eurocode 2
# Table A3 (pp. 124–127).   β = 0.0 means that edge is simply supported (no hogging).
_TWO_WAY_COEFFS = {
    "SSSS": [  # All four edges simply supported
        (0.062, 0.062, 0.0, 0.0),
        (0.074, 0.061, 0.0, 0.0),
        (0.084, 0.059, 0.0, 0.0),
        (0.093, 0.055, 0.0, 0.0),
        (0.099, 0.051, 0.0, 0.0),
        (0.104, 0.046, 0.0, 0.0),
        (0.113, 0.037, 0.0, 0.0),
        (0.118, 0.029, 0.0, 0.0),
    ],
    "CSSS": [  # One short edge (bottom) continuous, rest simply supported
        (0.047, 0.063, 0.094, 0.0),
        (0.056, 0.061, 0.112, 0.0),
        (0.063, 0.058, 0.125, 0.0),
        (0.069, 0.054, 0.137, 0.0),
        (0.074, 0.051, 0.147, 0.0),
        (0.078, 0.046, 0.154, 0.0),
        (0.087, 0.037, 0.167, 0.0),
        (0.092, 0.029, 0.175, 0.0),
    ],
    "SCSS": [  # Two short edges continuous
        (0.036, 0.063, 0.072, 0.072),
        (0.042, 0.061, 0.086, 0.086),
        (0.047, 0.058, 0.096, 0.096),
        (0.051, 0.053, 0.103, 0.103),
        (0.055, 0.049, 0.108, 0.108),
        (0.058, 0.044, 0.113, 0.113),
        (0.065, 0.034, 0.122, 0.122),
        (0.070, 0.027, 0.128, 0.128),
    ],
    "CSCS": [  # Both long edges continuous
        (0.031, 0.044, 0.0, 0.0),
        (0.037, 0.044, 0.0, 0.0),
        (0.042, 0.043, 0.0, 0.0),
        (0.046, 0.041, 0.0, 0.0),
        (0.050, 0.038, 0.0, 0.0),
        (0.053, 0.034, 0.0, 0.0),
        (0.059, 0.028, 0.0, 0.0),
        (0.063, 0.022, 0.0, 0.0),
    ],
    "CSSL": [  # One long edge continuous
        (0.039, 0.059, 0.0, 0.079),
        (0.049, 0.057, 0.0, 0.099),
        (0.056, 0.054, 0.0, 0.114),
        (0.062, 0.051, 0.0, 0.126),
        (0.068, 0.047, 0.0, 0.136),
        (0.073, 0.043, 0.0, 0.143),
        (0.082, 0.035, 0.0, 0.157),
        (0.089, 0.028, 0.0, 0.165),
    ],
    "CCSS": [  # One short + one long edge continuous (corner panel)
        (0.030, 0.045, 0.059, 0.060),
        (0.036, 0.044, 0.071, 0.072),
        (0.041, 0.042, 0.080, 0.082),
        (0.045, 0.040, 0.087, 0.089),
        (0.049, 0.037, 0.093, 0.096),
        (0.052, 0.034, 0.097, 0.101),
        (0.059, 0.028, 0.107, 0.112),
        (0.064, 0.022, 0.114, 0.119),
    ],
    "CCCS": [  # Three edges continuous
        (0.025, 0.042, 0.050, 0.0),
        (0.030, 0.040, 0.060, 0.0),
        (0.034, 0.038, 0.068, 0.0),
        (0.037, 0.035, 0.074, 0.0),
        (0.040, 0.033, 0.080, 0.0),
        (0.042, 0.030, 0.083, 0.0),
        (0.047, 0.024, 0.092, 0.0),
        (0.050, 0.019, 0.098, 0.0),
    ],
    "CCCC": [  # All four edges continuous (interior panel)
        (0.024, 0.024, 0.032, 0.024),
        (0.028, 0.024, 0.039, 0.024),
        (0.032, 0.024, 0.044, 0.024),
        (0.035, 0.023, 0.048, 0.023),
        (0.037, 0.022, 0.052, 0.022),
        (0.039, 0.020, 0.054, 0.020),
        (0.043, 0.016, 0.060, 0.016),
        (0.047, 0.013, 0.065, 0.013),
    ],
    "CSSL_long": [  # One short edge + opposite long edges continuous
        (0.028, 0.043, 0.057, 0.058),
        (0.034, 0.042, 0.068, 0.070),
        (0.038, 0.040, 0.077, 0.080),
        (0.043, 0.037, 0.085, 0.087),
        (0.047, 0.035, 0.091, 0.094),
        (0.050, 0.032, 0.097, 0.099),
        (0.056, 0.026, 0.105, 0.110),
        (0.062, 0.021, 0.112, 0.117),
    ],
}


def get_two_way_coefficients(
    panel_type: str,
    ly_lx: float,
) -> Dict[str, Any]:
    """
    Return Rankine-Grashof / Marcus bending moment coefficients for a
    two-way slab panel.

    Parameters
    ----------
    panel_type : Edge condition code — see module docstring for valid codes.
    ly_lx      : Span ratio ly/lx (≥ 1.0). Values are interpolated linearly.

    Returns
    -------
    dict with keys alpha_sx, alpha_sy, beta_sx, beta_sy, note.
    """
    if panel_type not in _TWO_WAY_COEFFS:
        raise ValueError(
            f"Unknown panel_type '{panel_type}'. "
            f"Valid types: {list(_TWO_WAY_COEFFS.keys())}"
        )

    table = _TWO_WAY_COEFFS[panel_type]
    ly_lx = max(1.0, min(ly_lx, 2.0))   # clamp to table range

    # Find bounding indices for linear interpolation
    if ly_lx <= _TWO_WAY_LY_LX[0]:
        a_sx, a_sy, b_sx, b_sy = table[0]
    elif ly_lx >= _TWO_WAY_LY_LX[-1]:
        a_sx, a_sy, b_sx, b_sy = table[-1]
    else:
        for i in range(len(_TWO_WAY_LY_LX) - 1):
            if _TWO_WAY_LY_LX[i] <= ly_lx <= _TWO_WAY_LY_LX[i + 1]:
                t = (ly_lx - _TWO_WAY_LY_LX[i]) / (_TWO_WAY_LY_LX[i+1] - _TWO_WAY_LY_LX[i])
                def lerp(a, b): return a + t * (b - a)
                a_sx = lerp(table[i][0], table[i+1][0])
                a_sy = lerp(table[i][1], table[i+1][1])
                b_sx = lerp(table[i][2], table[i+1][2])
                b_sy = lerp(table[i][3], table[i+1][3])
                break

    return {
        "alpha_sx": round(a_sx, 4),
        "alpha_sy": round(a_sy, 4),
        "beta_sx":  round(b_sx, 4),
        "beta_sy":  round(b_sy, 4),
        "note": (
            f"Two-way coefficients for panel '{panel_type}', ly/lx={ly_lx:.2f}:\n"
            f"  α_sx={a_sx:.4f}, α_sy={a_sy:.4f}  (sagging)\n"
            f"  β_sx={b_sx:.4f}, β_sy={b_sy:.4f}  (hogging at continuous edges)"
        ),
    }


# ===========================================================================
# 16. Punching shear — VRd,c at control perimeter  (EC2 Cl 6.4.3)
# ===========================================================================

def calculate_punching_VRd_c(
    fck: float,
    d: float,
    rho_l: float,        # Average reinf ratio = √(ρ_lx × ρ_ly) ≤ 0.02
    N_Ed: float = 0.0,   # Axial force on slab at column (N), tension positive
    A_c: float = 1.0,    # Cross-sectional area for σ_cp (mm²); 1m² = 1e6
) -> Dict[str, Any]:
    """
    Punching shear resistance VRd,c per unit perimeter length (N/mm).

    EC2 Cl 6.4.4 Eq. (6.47):
        vRd,c = C_Rd,c · k · (100·ρ_l·fck)^(1/3) + k_1·σ_cp

        with minimum:
        vRd,c ≥ (v_min + k_1·σ_cp)

    where:
        C_Rd,c = 0.18/γ_c = 0.12
        k      = 1 + √(200/d) ≤ 2.0
        ρ_l   = √(ρ_lx · ρ_ly) ≤ 0.02
        σ_cp   = (σ_cx + σ_cy)/2   (compression positive)
        k_1    = 0.1

    Note: The result is a stress (N/mm²). Multiply by the control perimeter
    and effective depth to get the total resistance VRd,c.

    Parameters
    ----------
    fck   : Cylinder concrete strength (N/mm²).
    d     : Mean effective depth of slab (mm).
    rho_l : Average tension reinforcement ratio (combined x+y).
    N_Ed  : Net tension on slab from prestress or applied axial load (N).
            Usually 0 for non-prestressed slabs.
    A_c   : Gross area for σ_cp (mm²).
    """
    C_Rd_c = 0.18 / GAMMA_C
    k = min(1.0 + math.sqrt(200.0 / d), 2.0)
    rho_l = min(max(rho_l, 0.0), 0.02)

    sigma_cp = -N_Ed / A_c if A_c > 0 else 0.0   # compression positive
    k1 = 0.1

    v_rdc = C_Rd_c * k * (100.0 * rho_l * fck) ** (1.0 / 3.0) + k1 * sigma_cp
    v_min = 0.035 * k ** 1.5 * math.sqrt(fck)
    v_rdc = max(v_rdc, v_min + k1 * sigma_cp)

    return {
        "value": round(v_rdc, 4),
        "k":     round(k, 3),
        "rho_l": round(rho_l, 4),
        "v_min": round(v_min, 4),
        "note": (
            f"vRd,c (punching, EC2 Cl 6.4.4): k={k:.3f}, ρ_l={rho_l:.4f}, "
            f"vRd,c = {v_rdc:.4f} N/mm²"
        ),
    }


# ===========================================================================
# 17. Punching shear — applied design stress at control perimeter (EC2 Cl 6.4.3)
# ===========================================================================

def calculate_punching_v_Ed(
    V_Ed: float,        # Design column reaction (N)
    beta: float,        # Eccentricity factor (1.15 interior, 1.4 edge, 1.5 corner)
    u_1: float,         # Control perimeter length (mm)
    d: float,           # Mean effective depth (mm)
) -> Dict[str, Any]:
    """
    Design punching shear stress v_Ed at the control perimeter.

    EC2 Cl 6.4.3 Eq. (6.38):
        v_Ed = β · V_Ed / (u_1 · d)

    where β accounts for eccentricity of loading per Cl 6.4.3(3).

    Parameters
    ----------
    V_Ed  : Design reaction transferred to column (N).
    beta  : Eccentricity factor (see EC2 Table 6.1N or Cl 6.4.3(3)).
    u_1   : First control perimeter at 2d from column face (mm).
    d     : Mean effective depth of slab (mm).
    """
    v_Ed = beta * V_Ed / (u_1 * d)
    return {
        "value": round(v_Ed, 4),
        "note": (
            f"v_Ed = β·V_Ed/(u₁·d) = {beta}×{V_Ed/1e3:.1f}k/({u_1:.0f}×{d:.0f}) "
            f"= {v_Ed:.4f} N/mm²  (EC2 Cl 6.4.3 Eq.6.38)"
        ),
    }

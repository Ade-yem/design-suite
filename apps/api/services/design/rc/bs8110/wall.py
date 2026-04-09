"""
BS 8110-1:1997  –  Reinforced Concrete Wall Design  (Clause 3.9)
=================================================================
``design_reinforced_wall`` is the single entry point for RC wall design.

Design sequence
---------------
1.  **Slenderness classification** (Cl 3.9.3.1)
       le/h ≤ 15 (braced) or ≤ 10 (unbraced) → stocky
       le/h >  limit                            → slender

2.  **Eccentricity check** (Cl 3.9.3.4)
       If M/N > 0.05h, the wall exceeds the minimum eccentricity limit.
       Design proceeds as a column (combined N+M).
       If M/N ≤ 0.05h, the simplified axial-only capacity formula applies.

3.  **Additional moment for slender walls** (Cl 3.9.3.5)
       M_add = N_v × e_add,  where e_add = h/2000 × (le/h)²
       This moment is added to the applied moment before final design.

4.  **Axial resistance / vertical steel** (Cl 3.9.3.7)
       Stocky braced walls (simplified formula):
           n_w = 0.35 × fcu × h + 0.67 × fy × Asc   [N/mm per unit length]
       Solving for Asc (mm²/m):
           Asc = (n_v − 0.35 × fcu × h) / (0.67 × fy / 1000)
               = (n_v − 0.35 × fcu × h) × 1000 / (0.67 × fy)
       Note: n_v is in N/mm (force per mm of wall length); Asc is mm²/m.

5.  **Vertical reinforcement selection** (Cl 3.12.5.3)

6.  **Horizontal reinforcement** (Cl 3.12.7.4)
       As_h ≥ max(0.25% bh for fy ≥ 460, 0.25 × As_v_prov)

7.  **Detailing checks** (Cl 3.12.7)
       Vertical bar spacing ≤ min(3h, 400 mm)
       Horizontal bar spacing ≤ min(3h, 400 mm)

8.  **In-plane shear check** (Cl 3.9.3.8)
       If horizontal shear V_h is provided, check v_h = V_h/(l_w × d) ≤ vc.

Scope and limitations
---------------------
  * This module handles **braced stocky walls** with full capacity calculation
    and **slender walls** with correct additional moment computation.
  * Walls with eccentricity > 0.05h are flagged and the additional moment
    is included in the design; the vertical steel is selected to carry the
    combined N + M using a simplified column check (tension/compression face
    approach analogous to Cl 3.8.4).
  * **Unbraced walls** receive a warning; the same procedure is used but
    with the unbraced slenderness limit.
  * Plain concrete walls (Cl 3.9.4) are outside scope.
"""

from __future__ import annotations

import math
from typing import Optional

from models.bs8110.wall import WallSection
from services.design.rc.bs8110.formulas import (
    calculate_k,
    calculate_k_prime,
    calculate_lever_arm,
    calculate_singly_reinforced_section,
    calculate_vc,
    check_shear_stress,
    check_reinforcement_limits,
)
from services.design.rc.common.select_reinforcement import select_slab_reinforcement


# ===========================================================================
# Main design function
# ===========================================================================

def design_reinforced_wall(
    section: WallSection,
    n_v: float,                        # Factored axial load intensity (N/mm per unit length)
    M: float = 0.0,                    # Factored bending moment per unit length (N·mm/m)
    V_h: Optional[float] = None,       # In-plane horizontal shear per unit length (N/mm)
) -> dict:
    """
    Design a 1 m strip of a reinforced concrete wall per BS 8110 Cl 3.9.

    Parameters
    ----------
    section : ``WallSection`` — geometry and material model.
    n_v     : Factored ultimate axial load intensity (N/mm of wall length).
              This is the design axial force per unit *horizontal* length, i.e.
              N_total / l_w  (not per metre height).  Must be positive (compression).
    M       : Factored design bending moment per unit length (N·mm/m).
              Moment is taken about the wall centroidal axis (bending about the
              wall thickness axis).  Use 0 for pure axial design.
    V_h     : In-plane horizontal shear intensity per unit length (N/mm). Optional.
              This is the total horizontal shear divided by the wall height.
              If provided, an in-plane shear check is performed (Cl 3.9.3.8).

    Returns
    -------
    dict with:
        status                    : ``"OK"`` or failure description.
        slenderness               : ``"Stocky"`` or ``"Slender"``.
        eccentricity_class        : ``"Axial"`` or ``"Column-strip (N+M)"``.
        n_capacity_concrete_kNm   : Concrete contribution to axial capacity (kN/m).
        As_req_v                  : Required vertical steel area (mm²/m).
        As_prov_v                 : Provided vertical steel (mm²/m).
        vertical_steel            : Bar description e.g. ``"H12 @ 150 c/c"``.
        As_req_h                  : Required horizontal steel (mm²/m).
        horizontal_steel          : Bar description.
        shear_status              : In-plane shear result (if V_h supplied).
        notes                     : List of calculation step strings.
        warnings                  : List of warning strings.
    """
    notes: list[str] = []
    warnings: list[str] = []
    results: dict = {"status": "OK", "notes": notes, "warnings": warnings}

    notes.append(section.summary())
    notes.append(
        f"Design actions: n_v = {n_v:.2f} N/mm  ({n_v:.0f} kN/m), "
        f"M = {M/1e6:.2f} kN·m/m  (BS 8110 Cl 3.9)"
    )

    h   = section.h
    fcu = section.fcu
    fy  = section.fy
    d   = section.d
    b   = 1000.0    # 1 m strip

    # =========================================================================
    # Step 1: Slenderness classification  (Cl 3.9.3.1)
    # =========================================================================
    slenderness = section.l_e / h
    # Stocky/slender boundary: 15 (braced) or 10 (unbraced) per Cl 3.9.3.1
    stocky_limit = 15 if section.braced else 10
    is_slender = slenderness > stocky_limit

    status_str = "Slender" if is_slender else "Stocky"
    results["slenderness"] = status_str
    notes.append(
        f"Slenderness: le/h = {slenderness:.1f}  (limit = {stocky_limit}, "
        f"{'braced' if section.braced else 'unbraced'}) → {status_str}  (Cl 3.9.3.1)"
    )

    if not section.braced:
        warnings.append(
            "Unbraced wall: the simplified stocky-wall capacity formula (Cl 3.9.3.7) "
            "is strictly for braced walls only. Consider full column interaction design."
        )

    # =========================================================================
    # Step 2: Eccentricity check — decide design regime  (Cl 3.9.3.4)
    # =========================================================================
    # Minimum eccentricity e_min = 0.05h (Cl 3.9.3.4)
    e_min = 0.05 * h
    # Applied eccentricity from moment
    e_applied = abs(M) / n_v if n_v > 0 else 0.0

    # Effective design eccentricity is the larger of applied and minimum
    e_design = max(e_applied, e_min)
    M_design = n_v * e_design  # N·mm/m (moment per metre width of wall)

    if e_applied > e_min:
        ecc_class = "Column-strip (N+M)"
        notes.append(
            f"Eccentricity e = M/N = {e_applied:.1f} mm > e_min = {e_min:.1f} mm (0.05h). "
            f"Wall must be designed as combined axial + flexure (Cl 3.9.3.4). "
            f"Design eccentricity e = {e_design:.1f} mm → M_design = {M_design/1e6:.2f} kN·m/m"
        )
    else:
        ecc_class = "Axial"
        notes.append(
            f"Eccentricity e = {e_applied:.1f} mm ≤ e_min = {e_min:.1f} mm (0.05h). "
            f"Simplified axial-only capacity formula applies (Cl 3.9.3.7). "
            f"Using e_min → M_design = N × e_min = {M_design/1e6:.2f} kN·m/m"
        )

    results["eccentricity_class"] = ecc_class

    # =========================================================================
    # Step 3: Additional moment for slender walls  (Cl 3.9.3.5)
    # =========================================================================
    if is_slender:
        # e_add = h/2000 × (le/h)²  per Cl 3.9.3.5 (same formula as columns)
        e_add = (h / 2000.0) * (slenderness ** 2)
        M_add = n_v * e_add   # N·mm/m
        notes.append(
            f"Slender wall — additional moment (Cl 3.9.3.5):\n"
            f"  e_add = h/2000 × (le/h)² = {h}/2000 × {slenderness:.1f}² = {e_add:.2f} mm\n"
            f"  M_add = n_v × e_add = {n_v:.2f} × {e_add:.2f} = {M_add/1e6:.2f} kN·m/m"
        )
        # Total design moment = max of (M_design + M_add) per Cl 3.9.3.5
        M_design = M_design + M_add
        notes.append(
            f"  Total design moment M_total = M_design + M_add = {M_design/1e6:.2f} kN·m/m"
        )

    # =========================================================================
    # Step 4: Axial capacity / required vertical steel  (Cl 3.9.3.7)
    # =========================================================================
    notes.append("--- Axial Capacity & Vertical Steel  (Cl 3.9.3.7) ---")

    # Concrete contribution to axial capacity per unit length (N/mm):
    # n_concrete = 0.35 × fcu × h  [N/mm²  ×  mm  = N/mm]
    n_concrete = 0.35 * fcu * h   # N/mm

    results["n_capacity_concrete_kNm"] = round(n_concrete / 1e3, 2)
    notes.append(
        f"Concrete capacity: n_concrete = 0.35 × fcu × h = 0.35 × {fcu} × {h} = "
        f"{n_concrete:.1f} N/mm = {n_concrete/1e3:.2f} kN/m  (Cl 3.9.3.7)"
    )

    if n_v <= n_concrete:
        # Concrete alone carries the axial load — provide minimum vertical steel
        As_req_v = section.As_min_v
        notes.append(
            f"n_v ({n_v:.2f} N/mm) ≤ n_concrete ({n_concrete:.1f} N/mm). "
            "Concrete alone carries axial load. Providing minimum vertical steel."
        )
    else:
        # Steel contribution required:
        # n_v = 0.35 fcu h + 0.67 fy × Asc/1000
        # → Asc [mm²/m] = (n_v − n_concrete) × 1000 / (0.67 × fy)
        As_req_v = (n_v - n_concrete) * 1000.0 / (0.67 * fy)
        notes.append(
            f"Steel required: Asc = (n_v − n_concrete) × 1000 / (0.67 × fy)\n"
            f"  = ({n_v:.2f} − {n_concrete:.1f}) × 1000 / (0.67 × {fy}) = {As_req_v:.1f} mm²/m"
        )

    results["As_req_v"] = round(As_req_v, 2)

    # =========================================================================
    # Step 5: Additional steel for bending  (M_design from eccentricity)
    # =========================================================================
    # If M_design > 0 (always, since e_min is applied), check if the axial
    # steel derived above also handles the bending.  For a wall under N+M we
    # use the same rectangular-stress-block K approach as a slab/column.
    # The tension face steel must satisfy both:
    #   (a) The axial contribution formula (As_req_v above, for compression face)
    #   (b) The moment demand (As_req_m, for tension face / reduced compression)
    #
    # Simplified approach (conservative):  take the larger of As_req_v and As_req_m.
    # Full interaction diagram is outside scope for this simplified module.

    notes.append("--- Flexural contribution check ---")
    k_prime_res = calculate_k_prime()
    K_prime = k_prime_res["value"]
    notes.append(k_prime_res["note"])

    k_res = calculate_k(M_design, fcu, b, d)
    K = k_res["value"]
    notes.append(k_res["note"])

    if K > K_prime:
        warnings.append(
            f"M_design moment K ({K:.4f}) > K' ({K_prime:.4f}). "
            "Wall section is inadequate for combined axial + eccentricity. "
            "Increase wall thickness h."
        )
        results["status"] = "Section Inadequate (moment)"
    else:
        z_res = calculate_lever_arm(d, K)
        notes.append(z_res["note"])
        As_req_m = calculate_singly_reinforced_section(M_design, fy, z_res["value"])["value"]
        notes.append(
            f"Moment demand: As_req_m = M/(0.95fy×z) = {M_design:.0f}/(0.95×{fy}×{z_res['value']:.0f}) "
            f"= {As_req_m:.1f} mm²/m"
        )
        # Final As_req_v is the maximum of axial demand and moment demand
        As_req_v_final = max(As_req_v, As_req_m, section.As_min_v)
        if As_req_v_final > As_req_v:
            notes.append(
                f"Moment governs: As_req increased from {As_req_v:.1f} to {As_req_v_final:.1f} mm²/m"
            )
        As_req_v = As_req_v_final
        results["As_req_v"] = round(As_req_v, 2)

    # =========================================================================
    # Step 6: Vertical bar selection and detailing checks
    # =========================================================================
    notes.append("--- Vertical Steel Selection ---")
    bars_v = select_slab_reinforcement(
        max(As_req_v, section.As_min_v), d, h, fy
    )
    results["As_prov_v"]     = bars_v["As_prov"]
    results["vertical_steel"] = bars_v["description"]
    if bars_v["warning"]:
        warnings.append(bars_v["warning"])
    notes.append(f"Vertical steel: {bars_v['description']}  (As_prov = {bars_v['As_prov']:.1f} mm²/m)")

    # Reinforcement limits
    lim_res = check_reinforcement_limits(
        bars_v["As_prov"], section.As_min_v, section.As_max_v, "vertical"
    )
    notes.append(lim_res["note"])
    if lim_res["status"] == "FAIL":
        results["status"] = "Reinforcement Limit Failure"

    # Vertical bar spacing detailing check (Cl 3.12.7.1)
    spacing_v_max = min(3.0 * h, 400.0)   # mm
    if bars_v["spacing"] > spacing_v_max:
        warnings.append(
            f"Vertical bar spacing ({bars_v['spacing']} mm) > limit "
            f"min(3h={3*h:.0f}, 400) = {spacing_v_max:.0f} mm  (Cl 3.12.7.1)."
        )
    notes.append(
        f"Vertical spacing limit: min(3h, 400) = {spacing_v_max:.0f} mm  "
        f"(provided {bars_v['spacing']} mm) — "
        + ("OK" if bars_v["spacing"] <= spacing_v_max else "EXCEED — see warning")
    )

    # =========================================================================
    # Step 7: Horizontal reinforcement  (Cl 3.12.7.4)
    # =========================================================================
    notes.append("--- Horizontal Steel  (Cl 3.12.7.4) ---")
    # As_h ≥ max(As_min_h, 0.25 × As_v_prov)  per Cl 3.12.7.4
    As_h_req = max(section.As_min_h, 0.25 * bars_v["As_prov"])
    bars_h = select_slab_reinforcement(As_h_req, d, h, fy)
    results["As_req_h"]       = round(As_h_req, 2)
    results["horizontal_steel"] = bars_h["description"]
    if bars_h["warning"]:
        warnings.append(bars_h["warning"])
    notes.append(
        f"As_h_req = max(As_min_h={section.As_min_h:.1f}, 0.25×As_v_prov={0.25*bars_v['As_prov']:.1f}) "
        f"= {As_h_req:.1f} mm²/m → {bars_h['description']}"
    )

    # Horizontal bar spacing limit (Cl 3.12.7.1)
    spacing_h_max = min(3.0 * h, 400.0)
    if bars_h["spacing"] > spacing_h_max:
        warnings.append(
            f"Horizontal bar spacing ({bars_h['spacing']} mm) > limit "
            f"{spacing_h_max:.0f} mm  (Cl 3.12.7.1)."
        )

    # =========================================================================
    # Step 8: In-plane horizontal shear check  (Cl 3.9.3.8)
    # =========================================================================
    if V_h is not None:
        notes.append("--- In-plane Shear Check  (Cl 3.9.3.8) ---")
        # Design shear stress: v_h = V_h / (l_w × d)
        # V_h is total horizontal shear force (N); l_w is wall length (mm)
        # Expressed per unit height gives v_h = V_h [N/mm] / d [mm]
        v_h = V_h / d   # N/mm² (V_h is per unit height = N/mm)
        notes.append(
            f"In-plane shear: v_h = V_h / d = {V_h:.2f} / {d:.0f} = {v_h:.4f} N/mm²  "
            f"(Cl 3.9.3.8)"
        )
        v_max = min(0.8 * math.sqrt(fcu), 5.0)
        if v_h > v_max:
            results["shear_status"] = f"FAIL: v_h ({v_h:.3f}) > v_max ({v_max:.3f})"
            if results["status"] == "OK":
                results["status"] = "In-plane Shear Failure"
        else:
            # Compare with vc for horizontal steel
            vc_res = calculate_vc(bars_h["As_prov"], 1000.0, d, fcu, h)
            vc = vc_res["value"]
            notes.append(vc_res["note"])
            if v_h <= vc:
                results["shear_status"] = f"OK: v_h ({v_h:.3f}) ≤ vc ({vc:.3f})"
            else:
                results["shear_status"] = (
                    f"Additional shear steel required: v_h ({v_h:.3f}) > vc ({vc:.3f})."
                )
                warnings.append(
                    f"In-plane shear v_h ({v_h:.3f}) > vc ({vc:.3f}). "
                    "Increase horizontal steel or wall thickness."
                )

    return results
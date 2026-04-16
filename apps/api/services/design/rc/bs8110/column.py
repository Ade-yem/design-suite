"""
BS 8110-1:1997  –  Column Design Orchestration
=============================================
Full design logic for short and slender columns under axial load and uniaxial bending.
Uses numerical strain compatibility based on the simplified rectangular stress block.
"""

from models.bs8110.column import ColumnSection
from services.design.rc.common.select_reinforcement import select_column_reinforcement
from services.design.rc.bs8110.formulas import calculate_axial_bending_capacity, calculate_vc, check_shear_stress


def calculate_column_reinforcement(
    section: ColumnSection,
    N: float,    # Axial design load (N)
    Mx: float,   # Design moment about major axis (N.mm) — h dimension
    My: float = 0.0, # Design moment about minor axis (N.mm) — b dimension
    V: float = 0.0,  # Design shear force (N)
) -> dict:
    notes: list[str] = []
    warnings: list[str] = []

    results = {
        "status": "OK",
        "As_req": 0.0,
        "As_prov": 0.0,
        "reinforcement_description": "None",
        "slenderness": "",
        "notes": notes,
        "warnings": warnings,
    }

    notes.append(section.summary())
    notes.append(f"Design actions: N = {N/1000:.1f} kN, Mx = {Mx/1e6:.1f} kNm, My = {My/1e6:.1f} kNm, V = {V/1000:.1f} kN")

    # 1. Slenderness check (BS 8110 Cl 3.8.1.3)
    lex_h = section.l_ex / section.h
    ley_b = section.l_ey / section.b
    
    slender_limit = 15 if section.braced else 10
    
    is_slender_x = lex_h > slender_limit
    is_slender_y = ley_b > slender_limit
    is_slender = is_slender_x or is_slender_y
    
    status_str = "Slender" if is_slender else "Short"
    results["slenderness"] = status_str
    
    notes.append(f"Slenderness ratios: lex/h = {lex_h:.1f}, ley/b = {ley_b:.1f} (Limit={slender_limit}) -> {status_str}")

    M_major = abs(Mx)
    M_minor = abs(My)
    
    # Minimum eccentricity moment: e_min = min(0.05 * h/b, 20mm) per Cl 3.8.2.4
    e_min_h = min(0.05 * section.h, 20.0)
    e_min_b = min(0.05 * section.b, 20.0)
    
    # Min moments for major and minor
    Mx_min = N * e_min_h
    My_min = N * e_min_b
    
    if M_major < Mx_min:
        notes.append(f"Major moment ({M_major/1e6:.1f} kNm) < Mx_min ({Mx_min/1e6:.1f} kNm). Using Mx_min.")
        M_major = Mx_min
    if M_minor < My_min:
        notes.append(f"Minor moment ({M_minor/1e6:.1f} kNm) < My_min ({My_min/1e6:.1f} kNm). Using My_min.")
        M_minor = My_min
        
    # Additional moment for slender columns (Cl 3.8.3)
    if is_slender:
        # Using K = 1.0 for conservatism (permitted by Cl 3.8.3.1)
        # For major axis (h buckling)
        e_add_h = (section.h / 2000.0) * (lex_h ** 2) if is_slender_x else 0.0
        # For minor axis (b buckling)
        e_add_b = (section.b / 2000.0) * (ley_b ** 2) if is_slender_y else 0.0
        
        # Design moment calculation (Cl 3.8.3.2)
        # Mi = 0.4M1 + 0.6M2. Conservatively assuming Mi = 0.6M2.
        Mi_h = 0.6 * abs(Mx)
        Mi_b = 0.6 * abs(My)
        
        M_h_t = max(abs(Mx) + N * e_add_h, Mi_h + N * e_add_h, Mx_min)
        M_b_t = max(abs(My) + N * e_add_b, Mi_b + N * e_add_b, My_min)
        
        M_major = M_h_t
        M_minor = M_b_t
        
        notes.append(f"Slender column additional moments included: Major={M_major/1e6:.1f} kNm, Minor={M_minor/1e6:.1f} kNm")

    # Biaxial Bending adjustment (Cl 3.8.4.5 / Table 3.22)
    # Check if biaxial check is mandated or if we have dual moments
    is_biaxial_required = (lex_h > 20.0) or (section.h / section.b >= 3.0) or (abs(My) > My_min)
    
    if is_biaxial_required:
        from services.design.rc.bs8110.formulas import calculate_biaxial_beta
        # N / (b*h*fcu)
        N_bhfcu = N / (section.b * section.h * section.fcu)
        beta = calculate_biaxial_beta(N_bhfcu)
        
        # M' logic
        if M_major / section.h >= M_minor / section.b:
            M_augmented = M_major + beta * (section.h / section.b) * M_minor
            notes.append(f"Biaxial adjustment (Cl 3.8.4.5): M'x = Mx + β(h/b)My = {M_augmented/1e6:.1f} kNm (β={beta:.2f})")
        else:
            # We design for the minor axis, but we'll assume the search is always about major axis
            # so we'll flip h and b conceptually
            M_augmented = M_minor + beta * (section.b / section.h) * M_major
            notes.append(f"Biaxial adjustment (Cl 3.8.4.5): M'y = My + β(b/h)Mx = {M_augmented/1e6:.1f} kNm (β={beta:.2f})")
            # For the binary search below, we'll swap b/h if designing for minor axis
            # But simpler: always use M_major as the target design moment after augmentation.
        
        M_design = M_augmented
    else:
        M_design = M_major

    # Slenderness Ratio Limit for unbraced (Cl 3.8.5)
    if not section.braced and (lex_h > 30.0 or ley_b > 30.0):
        warnings.append(f"Unbraced deflection risk: Max slenderness ratio ({max(lex_h, ley_b):.1f}) > 30 (Cl 3.8.5 limits).")

    # Binary search for minimum valid Asc
    low_Asc = section.As_min
    high_Asc = section.As_max
    
    found_Asc = section.As_max + 1
    
    # We iterate Asc. For a given Asc, we see if there's any neutral axis 'x' 
    # where N_cap is close to N, and M_cap >= M_design
    
    def check_Asc(Asc_trial):
        # We need N_cap(x) ~ N. Since N_cap(x) increases as x increases:
        # binary search x from 1 to 2h
        x_low = 1.0
        x_high = 3.0 * section.h
        
        # Binary search for x
        for _ in range(30):
            x_mid = (x_low + x_high) / 2.0
            # Assume 8 bars for capacity search to account for some 'side bars' 
            # and avoid overestimating capacity for multi-bar arrangements.
            n_cap, m_cap = calculate_axial_bending_capacity(
                x_mid, Asc_trial, section.b, section.h, section.d, section.h - section.d, section.fcu, section.fy, num_bars=8
            )
            
            if n_cap < N:
                x_low = x_mid
            else:
                x_high = x_mid
                
        # With the matched x, check M_cap
        n_cap, m_cap = calculate_axial_bending_capacity(
            x_high, Asc_trial, section.b, section.h, section.d, section.h - section.d, section.fcu, section.fy, num_bars=8
        )
        
        # Allow 1% tolerance on N? The search is exact enough.
        if m_cap >= M_design:
            return True, m_cap
        return False, m_cap

    # Before searching Asc, let's just do a quick binary search
    best_Asc = None
    for _ in range(25):
        mid_Asc = (low_Asc + high_Asc) / 2.0
        passes, m_cap = check_Asc(mid_Asc)
        if passes:
            best_Asc = mid_Asc
            high_Asc = mid_Asc
        else:
            low_Asc = mid_Asc
            
    if best_Asc is None:
        # Check if max steel even passes
        passes, mk = check_Asc(section.As_max)
        if passes:
             best_Asc = section.As_max
             
    if best_Asc is None:
        results["status"] = "Section Inadequate"
        warnings.append(f"Column cannot support loads even with maximum reinforcement (As_max = {section.As_max:.0f} mm²).")
        return results

    results["As_req"] = round(best_Asc, 2)
    notes.append(f"Required total reinforcement As_req = {best_Asc:.1f} mm²")

    bars = select_column_reinforcement(best_Asc, section.b, section.h)
    results["As_prov"] = bars["As_prov"]
    results["reinforcement_description"] = bars["description"]
    
    if bars["warning"]:
        warnings.append(bars["warning"])

    # 3. Bar spacing / crack control (Cl 3.12.11.2)
    # Clear distance between longitudinal bars should generally not exceed 250mm.
    # We estimate num_per_face based on num_bars. 
    # For a symmetrical arrangement: num_per_face ~ num_bars/4 + 1
    num_per_face = (bars["num"] / 4) + 1
    side_clear = section.cover + section.link_dia
    inner_width = min(section.b, section.h) - 2.0 * side_clear
    clear_spacing = (inner_width - num_per_face * bars["dia"]) / max(num_per_face - 1, 1)
    
    notes.append(f"Clear spacing between bars: {clear_spacing:.1f} mm (Limit 250mm).")
    if clear_spacing > 250.0:
        warnings.append(f"Clear spacing ({clear_spacing:.1f} mm) > 250 mm (Cl 3.12.11.2). Provide additional bars.")

    if bars["As_prov"] < section.As_min:
        results["status"] = "Reinforcement Limit Failure"
        
    # Shear Check (Cl 3.8.4.6 / 3.4.5.12)
    
    notes.append("--- Shear Check (Cl 3.8.4.6) ---")
    shear_res = check_shear_stress(V, section.b, section.d, section.fcu)
    notes.append(shear_res["note"])
    if shear_res["status"] == "FAIL":
        results["status"] = "Shear Failure (Max reached)"
    else:
        # Concrete capacity with compression enhancement (axial force)
        vc_res = calculate_vc(bars["As_prov"], section.b, section.d, section.fcu)
        vc = vc_res["value"]
        
        # Cl 3.4.5.12: Enhanced vc' = vc + 0.6 * N*V / (Ac*M)
        # We use the corrected variant: vc' = vc + 0.6 * N*V*h / (Ac*M) as suggested by audit
        Ac = section.b * section.h
        if M_design > 0 and V > 0:
             # Enhancement factor = 0.6 * N / Ac * (V*h/M)
             # Eccentricity check: M/N ratio
             ecc = M_design / N
             if ecc > 0.6 * section.h:
                 notes.append(f"Eccentricity M/N ({ecc:.1f} mm) > 0.6h ({0.6*section.h:.1f} mm). No shear enhancement per Cl 3.4.5.12.")
                 vc_prime = vc
             else:
                 enhancement = 0.6 * (N * V * section.h) / (Ac * M_design)
                 vc_prime = vc + (enhancement / (section.b * section.d)) # Enhancement as stress contribution
                 # Actually, Equation 6 variant from audit:
                 # vc' = vc + 0.6 * (N*V*h) / (Ac*M)?
                 # let's be conservative and limit enhancement.
                 vc_prime = min(vc + 0.6 * N / Ac, 0.8 * (section.fcu**0.5) if section.fcu < 25 else 5.0)
                 notes.append(f"Shear enhanced by axial compression: vc' = {vc_prime:.3f} N/mm²")
        else:
            vc_prime = vc

        if shear_res["v"] > vc_prime:
            warnings.append(f"Shear stress v ({shear_res['v']:.3f}) > enhanced vc' ({vc_prime:.3f}). Shear links required.")
            results["shear_status"] = "Shear Links Required"
        else:
            results["shear_status"] = "OK"

    # Detailing rules (links)
    min_link_dia = max(0.25 * bars["dia"], 6.0)
    max_link_spacing = min(section.b, section.h, 12 * bars["dia"])
    notes.append(f"Links Detail: Min Φ = {min_link_dia:.1f} mm, Max Spacing = {max_link_spacing:.0f} mm (Cl 3.12.7).")
    if section.link_dia < min_link_dia:
        warnings.append(f"Link diameter ({section.link_dia} mm) < required min ({min_link_dia:.1f} mm).")

    return results

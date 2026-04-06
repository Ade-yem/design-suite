"""
BS 8110-1:1997  –  Column Design Orchestration
=============================================
Full design logic for short and slender columns under axial load and uniaxial bending.
Uses numerical strain compatibility based on the simplified rectangular stress block.
"""

from models.column import ColumnSection
from services.calculations.common.select_reinforcement import select_column_reinforcement
from services.calculations.bs8110.formulas import calculate_axial_bending_capacity


def calculate_column_reinforcement(
    section: ColumnSection,
    N: float,   # Axial design load (N)
    M: float,   # Design moment about major axis (N.mm)
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
    notes.append(f"Design actions: N = {N/1000:.1f} kN, M = {M/1e6:.1f} kNm")

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

    M_design = abs(M)
    # Minimum eccentricity moment: N * 0.05 * h OR at least 20mm
    M_min = N * max(0.05 * section.h, 20.0)
    
    if M_design < M_min:
        notes.append(f"Applied moment ({M_design/1e6:.1f} kNm) < M_min ({M_min/1e6:.1f} kNm). Using M_min.")
        M_design = M_min
        
    # Additional moment for slender columns
    if is_slender:
        # e_add calculation per Cl 3.8.3.1
        # simplify βa = 1.0/2000 roughly, then e_add = h / 2000 * (le/b')^2 (simplified, full calc depends on K)
        # Using K = 1.0 for conservatism
        K_factor = 1.0
        # for uniaxial about major axis (h dimension), buckling is out of plane or in plane
        # let's assume worst slenderness drives e_add
        l_e_b_ratio = max(lex_h, ley_b)
        e_add = (section.h / 2000.0) * (l_e_b_ratio ** 2) * K_factor
        M_add = N * e_add
        notes.append(f"Slender column additional moment M_add = N * e_add = {M_add/1e6:.1f} kNm")
        M_design += M_add

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
            n_cap, m_cap = calculate_axial_bending_capacity(x_mid, Asc_trial, section.b, section.h, section.d, section.h - section.d, section.fcu, section.fy)
            
            if n_cap < N:
                x_low = x_mid
            else:
                x_high = x_mid
                
        # With the matched x, check M_cap
        # Or even better, check maximum possible M_cap for the given N? 
        # Since interaction diagram is bulb-shaped...
        n_cap, m_cap = calculate_axial_bending_capacity(x_high, Asc_trial, section.b, section.h, section.d, section.h - section.d, section.fcu, section.fy)
        
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

    if bars["As_prov"] < section.As_min:
        results["status"] = "Reinforcement Limit Failure"
        
    return results

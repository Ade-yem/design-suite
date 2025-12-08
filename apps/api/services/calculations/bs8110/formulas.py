import math
from typing import Union, Dict, Any

def calculate_k(M: float, fcu: float, b: float, d: float) -> Dict[str, Any]:
    """
    Calculate K factor.
    Ref: BS 8110-1:1997 Cl. 3.4.4.4
    K = M / (fcu * b * d^2)
    """
    K = M / (fcu * b * d**2)
    return {
        "value": K,
        "note": f"Calculated K = M / (fcu * b * d^2) = {K:.4f} (BS 8110 Cl. 3.4.4.4)"
    }

def calculate_lever_arm(d: float, K: float) -> Dict[str, Any]:
    """
    Calculate lever arm z.
    Ref: BS 8110-1:1997 Cl. 3.4.4.4
    z = d * (0.5 + sqrt(0.25 - K/0.9))
    Max z = 0.95d
    """
    try:
        term = 0.25 - (K / 0.9)
        if term < 0:
            return {"value": 0, "note": "K > 0.225, lever arm formula invalid (Compression steel required)"}
        
        z = d * (0.5 + math.sqrt(term))
        z_limited = min(z, 0.95 * d)
        note = f"Calculated z = d * (0.5 + sqrt(0.25 - K/0.9)) = {z:.1f} mm"
        if z > 0.95 * d:
            note += f", limited to 0.95d ({z_limited:.1f} mm)"
        note += " (BS 8110 Cl. 3.4.4.4)"
        
        return {"value": z_limited, "note": note}
    except ValueError:
        return {"value": 0, "note": "Error calculating lever arm"}

def calculate_singly_reinforced_section(M: float, fy: float, z: float) -> Dict[str, Any]:
    """
    Calculate tension steel for singly reinforced section.
    Ref: BS 8110-1:1997 Cl. 3.4.4.4
    As = M / (0.95 * fy * z)
    """
    As = M / (0.95 * fy * z)
    return {
        "value": As,
        "note": f"Calculated As = M / (0.95 * fy * z) = {As:.1f} mm2 (BS 8110 Cl. 3.4.4.4)"
    }

def calculate_doubly_reinforced_section(M: float, fcu: float, fy: float, b: float, d: float, d_prime: float, K: float) -> Dict[str, Any]:
    """
    Calculate tension and compression steel.
    Ref: BS 8110-1:1997 Cl. 3.4.4.4
    """
    K_prime = 0.156
    
    # Moment capacity of singly reinforced section
    # Mu = 0.156 * fcu * b * d^2
    M_u = K_prime * fcu * b * d**2
    
    # Excess moment
    M_add = M - M_u
    
    # Compression steel
    # As' = (M - Mu) / (0.95 * fy * (d - d'))
    As_prime = M_add / (0.95 * fy * (d - d_prime))
    
    # Tension steel
    # As = (Mu / (0.95 * fy * z)) + As'
    # For K=K', z = 0.775d
    z = 0.775 * d if (K == K_prime) else calculate_lever_arm(d, K)["value"]
    As = (M_u / (0.95 * fy * z)) + As_prime
    
    return {
        "As_req": As,
        "As_prime_req": As_prime,
        "z": z,
        "note": f"Doubly Reinforced: As' = (M-Mu)/(0.95*fy*(d-d')) = {As_prime:.1f} mm2, As = (Mu/(0.95*fy*z)) + As' = {As:.1f} mm2 (BS 8110 Cl. 3.4.4.4)"
    }

def check_shear_stress(V: float, b: float, d: float, fcu: float) -> Dict[str, Any]:
    """
    Check shear stress v.
    Ref: BS 8110-1:1997 Cl. 3.4.5.2
    v = V / (b * d)
    v_max = 0.8 * sqrt(fcu) or 5 N/mm2
    """
    v = V / (b * d)
    v_max = min(0.8 * math.sqrt(fcu), 5.0)
    
    status = "OK" if v <= v_max else "FAIL"
    return {
        "v": v,
        "v_max": v_max,
        "status": status,
        "note": f"Shear stress v = V/(bd) = {v:.2f} N/mm2. Max v = {v_max:.2f} N/mm2 (BS 8110 Cl. 3.4.5.2)"
    }

def calculate_shear_links(v: float, vc: float, b: float, fyv: float, d: float) -> Dict[str, Any]:
    """
    Determine shear links.
    Ref: BS 8110-1:1997 Table 3.8
    """
    note = ""
    links = ""
    
    if v < 0.5 * vc:
        links = "Nominal links"
        note = f"v ({v:.2f}) < 0.5*vc ({0.5*vc:.2f}): Nominal links required (Table 3.8)"
    elif v < (vc + 0.4):
        links = "Minimum links"
        note = f"0.5*vc < v ({v:.2f}) < vc+0.4: Minimum links required (Table 3.8)"
    else:
        # Design links
        # Asv/sv >= b * (v - vc) / (0.95 * fyv)
        # Assume H8-2 legs (Asv = 100 mm2)
        Asv = 100.5
        sv = 0.95 * fyv * Asv / (b * (v - vc))
        sv = min(sv, 0.75 * d)
        links = f"H8 @ {int(sv)} mm c/c"
        note = f"v ({v:.2f}) > vc+0.4: Designed links required. Asv/sv = b(v-vc)/(0.95fyv). Provided {links} (Table 3.8)"
        
    return {
        "links": links,
        "note": note
    }

def calculate_design_service_stress(fy: float, As_req: float, As_prov: float, beta_b: float = 1.0) -> float:
    """
    Calculate design service stress fs.
    Ref: BS 8110-1:1997 Cl. 3.4..5
    fs = 2 * fy * As_req / (3 * As_prov * beta_b)
    """
    if As_prov == 0:
        return 0
    return 2 * fy * As_req / (3 * As_prov * beta_b)

def check_deflection(span: float,
                     d: float,
                     basic_ratio: float,
                     As_prov: float,
                     As_req: float,
                     b: float,
                     M: float,
                     fy: float,
                     As_prime_prov: float = 0,
                     ) -> Dict[str, Any]:
    """
    Deflection check using span/depth ratio.
    Ref: BS 8110-1:1997 Cl. 3.4.6 & Table 3.10, 3.11
    """
    fs = calculate_design_service_stress(fy, As_req, As_prov)
    
    # Modification factor for tension reinforcement (MFt)
    # MFt = 0.55 + (477 - fs) / (120 * (0.9 + (M / (b * d**2))))
    # Limit: MFt <= 2.0
    try:
        m_bd2 = M / (b * d**2)
        MFt = 0.55 + (477 - fs) / (120 * (0.9 + m_bd2))
        MFt = min(MFt, 2.0)
        MFt = max(MFt, 0.1) # Safety floor? Code implies positive.
    except ZeroDivisionError:
        MFt = 1.0

    # Modification factor for compression reinforcement (MFc)
    # MFc = 1 + (100 * As'_prov / (b * d)) / (3 + (100 * As'_prov / (b * d)))
    # Limit: MFc <= 1.5
    try:
        pct_comp = 100 * As_prime_prov / (b * d)
        MFc = 1 + (pct_comp / (3 + pct_comp))
        MFc = min(MFc, 1.5)
    except ZeroDivisionError:
        MFc = 1.0
        
    MF = MFc * MFt
    allowable_ratio = basic_ratio * MF
    actual_ratio = span / d
    
    status = "OK" if actual_ratio <= allowable_ratio else "FAIL"
    
    note = (f"Deflection Check (BS 8110 Cl. 3.4.6): "
            f"Actual L/d = {actual_ratio:.2f}. "
            f"Allowable L/d = Basic ({basic_ratio}) * MFt ({MFt:.2f}) * MFc ({MFc:.2f}) = {allowable_ratio:.2f}. "
            f"fs = {fs:.2f} N/mm2. "
            f"Status: {status}")
            
    return {
        "actual": actual_ratio,
        "allowable": allowable_ratio,
        "status": status,
        "note": note
    }

def determine_basic_ratio(section: str, support_condition: str) -> float:
    """
    Determine basic span/depth ratio based on section type.
    Ref: BS 8110-1:1997 Cl. 3.4.6.3
    
    Args:
        section: Section type ("rectangular", "flanged")
        support_condition: Support condition ("simple", "cantilever", "continuous")
    """
    if section == "rectangular":
        if support_condition == "simple":
            return 20.0
        elif support_condition == "cantilever":
            return 7.0
        elif support_condition == "continuous":
            return 26.0
    elif section == "flanged":
        if support_condition == "simple":
            return 16.0
        elif support_condition == "cantilever":
            return 5.6
        elif support_condition == "continuous":
            return 20.8
    return 20.0 # Default fallback
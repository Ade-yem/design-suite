from services.calculations.common import select_reinforcement
from services.calculations.eurocode2.formulas import calculate_k_ec2
import math

def calculate_reinforcement(
    M: float, 
    V: float, 
    b: float, 
    d: float, 
    fck: float = 30, 
    fyk: float = 500
) -> dict:
    """
    Calculate required reinforcement for a rectangular beam per Eurocode 2.
    
    Args:
        M: Design Moment (Nmm)
        V: Design Shear (N)
        b: Width (mm)
        d: Effective depth (mm)
        fck: Concrete cylinder strength (N/mm2)
        fyk: Steel yield strength (N/mm2)
        
    Returns:
        Dictionary with As_req (mm2), shear_links, and status.
    """
    
    # 1. Bending Design
    # K = M / (b * d^2 * fck)
    K = M / (b * d**2 * fck)
    K_bal = 0.167 # Simplified limit for singly reinforced
    
    results = {
        "status": "OK",
        "As_req": 0,
        "As_prov": 0,
        "shear_links": "",
        "notes": []
    }
    
    if K > K_bal:
        results["status"] = "Compression Reinforcement Required"
        results["notes"].append(f"K ({K:.3f}) > K_bal (0.167).")
        # Simplified: Return max singly reinforced
        z = 0.82 * d
        As_req = M / (fyk / 1.15 * z) # fyd = fyk/1.15
    else:
        # z = d * [0.5 + sqrt(0.25 - K/1.134)]
        # 1.134 comes from 1.0 * 0.85 * fck / 1.5 (simplified)
        # Standard formula: z = d/2 * (1 + sqrt(1 - 3.53*K))
        try:
            term = 1 - 3.53 * K
            if term < 0:
                 z = 0.82 * d # Fallback
            else:
                z = (d / 2) * (1 + math.sqrt(term))
                z = min(z, 0.95 * d)
        except ValueError:
            z = 0.82 * d

        fyd = fyk / 1.15
        As_req = M / (fyd * z)
        results["As_req"] = round(As_req, 2)
        
    # 2. Shear Design (Simplified VRd,c check)
    # VRd,c = [Crd,c * k * (100 * rho_l * fck)^(1/3)] * b * d
    k = 1 + math.sqrt(200 / d)
    k = min(k, 2.0)
    rho_l = As_req / (b * d)
    rho_l = min(rho_l, 0.02)
    
    Crd_c = 0.18 / 1.5
    v_min = 0.035 * k**(1.5) * math.sqrt(fck)
    
    VRd_c = (Crd_c * k * (100 * rho_l * fck)**(1/3)) * b * d
    VRd_c = max(VRd_c, v_min * b * d)
    
    if V < VRd_c:
        results["shear_links"] = "Minimum links"
    else:
        results["shear_links"] = "Designed links required"
        results["notes"].append(f"VEd ({V/1000:.1f} kN) > VRd,c ({VRd_c/1000:.1f} kN)")

    return results

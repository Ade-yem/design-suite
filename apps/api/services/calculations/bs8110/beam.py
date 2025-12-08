from services.calculations.common import select_reinforcement
from services.calculations.bs8110.formulas import (
    calculate_k, 
    calculate_lever_arm, 
    calculate_singly_reinforced_section,
    calculate_doubly_reinforced_section,
    check_shear_stress,
    calculate_shear_links,
    check_deflection,
    determine_basic_ratio
)
import math

def calculate_beam_reinforcement(
    M: float, 
    V: float, 
    b: float, 
    d: float, 
    h: float,
    span: float,
    fcu: float = 30, 
    fy: float = 460, 
    fyv: float = 250
) -> dict:
    """
    Calculate required reinforcement for a rectangular beam per BS 8110.
    
    Args:
        M: Design Moment (Nmm)
        V: Design Shear (N)
        b: Width (mm)
        d: Effective depth (mm)
        h: Overall depth of the beam (mm)
        fcu: Concrete strength (N/mm2)
        fy: Steel yield strength (N/mm2)
        fyv: Shear link strength (N/mm2)
        span: Span of the beam (mm)
    
    Returns:
        Dictionary with As_req (mm2), shear_links, and status.
    """
    
    notes = []
    results = {
        "status": "OK",
        "As_req": 0,
        "As_prov": 0,
        "reinforcement_description": "None",
        "As_prime_req": 0,
        "As_prime_prov": 0,
        "compression_reinforcement_description": "None",
        "shear_links": "",
        "deflection_check": "",
        "notes": notes
    }
    
    # 1. Determine K
    k_res = calculate_k(M, fcu, b, d)
    K = k_res["value"]
    notes.append(k_res["note"])
    
    K_prime = 0.156
    
    # 2. Check if K > K_prime
    if K > K_prime:
        notes.append(f"K ({K:.3f}) > K' ({K_prime}). Compression reinforcement required.")
        
        # 7. Calculate As and As' (Doubly Reinforced)
        d_prime = h - d # Approximation
        if d_prime <= 0: d_prime = 50
        
        dr_res = calculate_doubly_reinforced_section(M, fcu, fy, b, d, d_prime, K)
        As_req = dr_res["As_req"]
        As_prime_req = dr_res["As_prime_req"]
        notes.append(dr_res["note"])
        
        results["As_req"] = round(As_req, 2)
        results["As_prime_req"] = round(As_prime_req, 2)
        
        # 8. Calculate As_prov for As'
        comp_bars = select_reinforcement(As_prime_req)
        results["As_prime_prov"] = comp_bars["As_prov"]
        results["compression_reinforcement_description"] = comp_bars["description"]
        notes.append(f"Provided Compression: {comp_bars['description']} ({comp_bars['As_prov']} mm2)")
        
    else:
        # 3. K < K_prime
        notes.append(f"K ({K:.3f}) <= K' ({K_prime}). Singly reinforced section.")
        
        # 4. Determine lever arm
        z_res = calculate_lever_arm(d, K)
        z = z_res["value"]
        notes.append(z_res["note"])
        
        # 5. Find As_req
        sr_res = calculate_singly_reinforced_section(M, fy, z)
        As_req = sr_res["value"]
        results["As_req"] = round(As_req, 2)
        notes.append(sr_res["note"])

    # 6. Find As_prov (Tension)
    tens_bars = select_reinforcement(As_req)
    results["As_prov"] = tens_bars["As_prov"]
    results["reinforcement_description"] = tens_bars["description"]
    notes.append(f"Provided Tension: {tens_bars['description']} ({tens_bars['As_prov']} mm2)")
    
    # 9. Check Deflection
    # TODO: Add support for cantilever and continuous beams
    # For now, the beam is simply supported, it is a rectangular section
    basic_ratio = determine_basic_ratio("rectangular", "simple")
    
    # Pass As_prime_prov if available
    As_prime_prov = results.get("As_prime_prov", 0)
    
    def_res = check_deflection(
        span=span, 
        d=d, 
        basic_ratio=basic_ratio, 
        As_prov=tens_bars["As_prov"], 
        As_req=As_req, 
        b=b, 
        M=M, 
        fy=fy,
        As_prime_prov=As_prime_prov
    )
    results["deflection_check"] = def_res["status"]
    notes.append(def_res["note"])

    if (def_res["status"] == "FAIL"):
        results["status"] = "Deflection Failure"
        notes.append("CRITICAL: Deflection exceeds maximum allowable.")
        return results

    
    # 10. Check Shear
    shear_res = check_shear_stress(V, b, d, fcu)
    notes.append(shear_res["note"])
    
    if shear_res["status"] == "FAIL":
        results["status"] = "Shear Failure"
        notes.append("CRITICAL: Shear stress exceeds maximum allowable.")
        return results

    # 11. Check Shear Links
    # Calculate vc (simplified)
    pt = 100 * results["As_prov"] / (b * d)
    pt = min(pt, 3.0)
    depth_factor = max(1.0, (400 / d)**0.25)
    vc = 0.79 * (pt)**(1/3) * depth_factor / 1.25 # /1.25 for safety factor? BS 8110 uses partial factor 1.25 for concrete shear? 
    # Actually BS 8110 Table 3.8 values are design values vc. The formula usually includes 1.25 if deriving from characteristic.
    # Let's assume standard formula for vc design value directly.
    # vc = 0.79 * (pt)^(1/3) * (400/d)^(1/4) / 1.25 (gamma_m)
    vc = min(vc, 0.8 * math.sqrt(fcu))
    notes.append(f"Calculated design concrete shear stress vc = {vc:.2f} N/mm2")

    # 12. Design Shear Reinforcement
    link_res = calculate_shear_links(shear_res["v"], vc, b, fyv, d)
    results["shear_links"] = link_res["links"]
    notes.append(link_res["note"])

    return results

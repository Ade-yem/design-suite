import math

def select_reinforcement(As_req: float) -> dict:
    """
    Select standard bars to satisfy As_req.
    Returns dict with bars (e.g., "3H20") and As_prov.
    """
    if As_req <= 0:
        return {"description": "None", "As_prov": 0}
        
    # Standard bars: 10, 12, 16, 20, 25, 32, 40
    bars = [10, 12, 16, 20, 25, 32, 40]
    best_fit = None
    min_excess = float('inf')
    
    # Simple heuristic: Try to find 2 to 4 bars that fit
    for num_bars in range(2, 6):
        for dia in bars:
            area = num_bars * math.pi * (dia/2)**2
            if area >= As_req:
                excess = area - As_req
                if excess < min_excess:
                    min_excess = excess
                    best_fit = {
                        "description": f"{num_bars}H{dia}",
                        "As_prov": round(area, 2),
                        "dia": dia,
                        "num": num_bars
                    }
                break 
    
    if not best_fit:
        return {
            "description": f"Provide > {int(As_req)} mm2",
            "As_prov": As_req
        }
        
    return best_fit




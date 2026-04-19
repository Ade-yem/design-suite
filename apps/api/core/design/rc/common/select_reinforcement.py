"""
select_beam_reinforcement  –  Calculates the reinforcement section
"""

import math
from typing import Optional

# ---------------------------------------------------------------------------
# Standard bar diameters (mm) — UK practice
# ---------------------------------------------------------------------------
STANDARD_DIAMETERS = [8, 10, 12, 16, 20, 25, 32, 40]
VALID_SPACINGS = [75, 100, 125, 150, 175, 200, 225, 250, 275, 300]


def select_beam_reinforcement(
    As_req: float,
    b_available: Optional[float] = None,
    cover: float = 25.0,
    link_dia: float = 8.0,
) -> dict:
    """
    Select standard deformed bars (Type H / HY) to satisfy ``As_req``.

    The function tries 2–8 bars across all standard diameters, picking the
    arrangement with the least over-provision.  If ``b_available`` is given,
    it also checks whether the bars fit within the beam width (enforcing the
    minimum clear gap of max(bar_dia, 25 mm) per BS 8110 Cl 3.12.11.1).
    If a single layer cannot fit, a two-layer arrangement is suggested.

    Parameters
    ----------
    As_req      : Required steel area (mm²).
    b_available : Beam width (mm) for spacing check.  Optional.
    cover       : Nominal side cover to links (mm).  Default 25 mm.
    link_dia    : Link bar diameter (mm).  Default 8 mm.

    Returns
    -------
    dict with keys:
        description : str    e.g. ``"3H20"``
        As_prov     : float  mm²
        dia         : int    bar diameter (mm)
        num         : int    number of bars
        fits        : bool   whether bars fit in one layer
        layers      : int    suggested number of layers (1 or 2)
        clear_space : float  actual clear gap between bars in one layer (mm)
        warning     : str    any spacing / capacity warning
    """
    if As_req <= 0:
        return {
            "description": "None", "As_prov": 0.0, "dia": 0, "num": 0,
            "fits": True, "layers": 1, "clear_space": 0.0, "warning": "",
        }

    best = None
    min_excess = float("inf")

    for num_bars in range(2, 9):
        for dia in STANDARD_DIAMETERS:
            area = num_bars * math.pi * (dia / 2.0) ** 2
            if area >= As_req:
                excess = area - As_req
                if excess < min_excess:
                    min_excess = excess
                    best = {
                        "description": f"{num_bars}H{dia}",
                        "As_prov": round(area, 2),
                        "dia": dia,
                        "num": num_bars,
                        "fits": True,
                        "layers": 1,
                        "clear_space": 0.0,
                        "warning": "",
                    }
                break  # smallest excess dia for this num_bars

    if best is None:
        return {
            "description": f"Provide > {int(As_req)} mm²",
            "As_prov": As_req, "dia": 0, "num": 0,
            "fits": False, "layers": 1, "clear_space": 0.0,
            "warning": f"Cannot satisfy As_req = {As_req:.0f} mm² with up to 8 bars.",
        }

    # --- Bar-spacing / width check (BS 8110 Cl 3.12.11.1) ---
    if b_available is not None and b_available > 0:
        dia = best["dia"]
        num = best["num"]
        side_clear = cover + link_dia          # each side
        min_clear_gap = max(float(dia), 25.0)  # Cl 3.12.11.1
        gaps = num - 1

        # Total minimum width required for one layer
        total_min_width = (
            num * dia
            + gaps * min_clear_gap
            + 2.0 * side_clear
        )

        # Actual clear gap available per inter-bar space
        inner_width = b_available - 2.0 * side_clear
        clear_per_gap = (inner_width - num * dia) / max(gaps, 1)
        best["clear_space"] = round(clear_per_gap, 1)

        if total_min_width > b_available:
            # Try fitting in 2 layers
            num_per_layer = math.ceil(num / 2)
            total_min_2lay = (
                num_per_layer * dia
                + (num_per_layer - 1) * min_clear_gap
                + 2.0 * side_clear
            )
            if total_min_2lay <= b_available:
                best["layers"] = 2
                best["warning"] = (
                    f"Bars ({num}H{dia}) do not fit in one layer "
                    f"(need {total_min_width:.0f} mm, beam is {b_available:.0f} mm). "
                    f"Arrange in 2 layers."
                )
            else:
                best["fits"] = False
                best["warning"] = (
                    f"Bars ({num}H{dia}) do not fit even in 2 layers "
                    f"(need ≥ {total_min_2lay:.0f} mm wide beam)."
                )

    return best


def select_slab_reinforcement(As_req: float, d: float, h: float, fy: float, beta_b: float = 1.0) -> dict:
    """
    Select standard deformed bars spacing per meter for solid slabs.
    BS 8110 Cl 3.12.11.2.7 maximum spacing = 3d or 750mm.
    For h > 200mm, stricter limits from Table 3.28 apply to control cracking.
    """
    if As_req <= 0:
         return {"description": "None", "As_prov": 0.0, "spacing": 0, "dia": 0, "warning": ""}
         
    best = None
    min_excess = float("inf")
    
    # 1. Basic limit (Cl 3.12.11.2.7)
    limit_3d = min(3 * d, 750.0)
    
    # 2. Crack control limit (Table 3.28 / Cl 3.12.11.2)
    # For h > 200mm, stricter limits from Table 3.28 apply.
    # Production recommendation: cap spacing regardless of h to ensure crack control.
    if fy >= 500:
        limit_table_328 = 120.0 + 100.0 * (beta_b - 0.7)  # approx 150 @ 1.0, 120 @ 0.7
    elif fy >= 460:
        limit_table_328 = 130.0 + 100.0 * (beta_b - 0.7)  # 160 @ 1.0, 130 @ 0.7
    else:
        limit_table_328 = 300.0

    # Production hard cap (User recommendation)
    hard_cap = 150.0 if fy >= 500 else (160.0 if fy >= 460 else 300.0)
            
    for dia in STANDARD_DIAMETERS:
        Abar = math.pi * (dia / 2.0)**2
        # required spacing to achieve As_req over 1000mm width
        s_req = (1000.0 * Abar) / As_req
        
        # for each spacing, we check if it satisfies BOTH limits
        # Note: Table 3.28 is CLEAR spacing. clear = s - dia.
        # But Cl 3.12.11.2.6 says if 100As/bd < 0.3%, Table 3.28 limits are replaced by 3d.
        
        valid_s = []
        for s in VALID_SPACINGS:
            if s > s_req:
                continue
            
            # Check 3d limit
            if s > limit_3d:
                continue
                
            # Check Table 3.28 limit / Hard cap
            is_thin = (h <= 200.0)
            pt_prov = 100.0 * (1000.0 * Abar / s) / (1000.0 * d)
            
            # If not thin AND pt > 0.3%, apply Table 3.28 clear spacing limit
            if not is_thin and pt_prov > 0.3:
                if (s - dia) > limit_table_328:
                    continue
            
            # Apply production hard cap for high strength steel regardless of h
            if s > hard_cap:
                continue
            
            valid_s.append(s)

        if valid_s:
            s_chosen = max(valid_s)
            As_prov = (1000.0 * Abar) / s_chosen
            excess = As_prov - As_req
            if excess < min_excess:
                min_excess = excess
                best = {
                    "description": f"H{dia} @ {s_chosen} c/c",
                    "As_prov": round(As_prov, 2),
                    "spacing": s_chosen,
                    "dia": dia,
                    "warning": ""
                }
    
    if best is None:
        return {
             "description": "Provide > max spacing limits",
             "As_prov": As_req, "spacing": 0, "dia": 0,
             "warning": f"Could not find standard spacing satisfying As_req={As_req:.1f} mm² considering crack control limits."
        }
    return best

def select_column_reinforcement(
    As_req: float,
    b: float,
    h: float,
) -> dict:
    """
    Select an even number of standard deformed bars for a rectangular column.
    Minimum 4 bars (one in each corner).
    """
    if As_req <= 0:
        return {"description": "None", "As_prov": 0.0, "dia": 0, "num": 0, "warning": ""}

    best = None
    min_excess = float("inf")
    
    # Typical column bar arrangements: 4, 6, 8, 10, 12 bars
    for num_bars in [4, 6, 8, 10, 12]:
        for dia in STANDARD_DIAMETERS:
            # Columns typically don't use 8mm or 10mm for main bars
            if dia < 12:
                continue
                
            area = num_bars * math.pi * (dia / 2.0) ** 2
            if area >= As_req:
                excess = area - As_req
                if excess < min_excess:
                    min_excess = excess
                    best = {
                        "description": f"{num_bars}H{dia}",
                        "As_prov": round(area, 2),
                        "dia": dia,
                        "num": num_bars,
                        "warning": ""
                    }
                break
                
    if best is None:
        return {
            "description": f"Provide > {int(As_req)} mm²",
            "As_prov": As_req, "dia": 0, "num": 0,
            "warning": f"Cannot satisfy As_req = {As_req:.0f} mm² with up to 12 standard bars."
        }
        
    return best


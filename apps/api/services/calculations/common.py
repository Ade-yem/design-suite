"""
common.py  –  Shared calculation utilities
==========================================
Utility functions used across all design standards.
Section / model objects live in ``models/calculations/``.
"""

import math
from typing import Optional

# ---------------------------------------------------------------------------
# Standard bar diameters (mm) — UK practice
# ---------------------------------------------------------------------------
STANDARD_DIAMETERS = [10, 12, 16, 20, 25, 32, 40]


def select_reinforcement(
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

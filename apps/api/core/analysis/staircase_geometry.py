"""
Storey-height-driven staircase flight geometry.

A flight rises exactly one storey, so its geometry is *determined* by the storey
height — it is not free. Previously the staircase solver and designer fell back to
fixed defaults (``num_steps=10, riser=175, L_plan=4.0``) that ignored storey
height entirely, so a stair could be modelled that did not physically connect the
two floors it sits between (wrong slope self-weight, wrong span).

This derives a code-consistent flight from the storey height:

  risers = round(storey_height / target_riser)        # whole number of risers
  riser  = storey_height / risers                      # exact → risers·riser == H
  going  = clamp(600 − 2·riser, ≥ min_going)           # 2R + G ≈ 600 mm comfort rule
  treads = risers − 1                                   # one fewer going than risers
  span   = treads · going + landing                     # plan length of flight + landing

Engineer-supplied values in ``overrides`` always win.
"""
from __future__ import annotations

from typing import Any, Dict

TARGET_RISER_MM = 175.0   # typical comfortable riser
MIN_GOING_MM = 250.0      # BS 8110 minimum going
DEFAULT_LANDING_MM = 1000.0
DEFAULT_WAIST_MM = 150.0
_TWO_R_PLUS_G = 600.0      # 2R + G comfort relationship


def derive_flight_geometry(
    storey_height_m: float,
    *,
    target_riser_mm: float = TARGET_RISER_MM,
    landing_mm: float = DEFAULT_LANDING_MM,
    waist_mm: float = DEFAULT_WAIST_MM,
    **overrides: Any,
) -> Dict[str, float]:
    """
    Derive a single flight's geometry from the building storey height.

    Parameters
    ----------
    storey_height_m : float
        Floor-to-floor height the flight must rise (m).
    target_riser_mm : float
        Preferred riser used to pick the riser count; the actual riser is then
        back-solved so ``risers × riser`` equals the storey height exactly.
    landing_mm, waist_mm : float
        Landing length and waist thickness defaults.
    overrides : Any
        Explicit engineer values (``riser``, ``going``/``tread``, ``num_steps``,
        ``span``/``L_plan_m``, ``waist``) that take precedence.

    Returns
    -------
    dict
        ``{num_risers, riser, going, num_steps, span_mm, L_plan_m, waist_mm,
        landing_mm}`` — millimetres unless suffixed ``_m``.
    """
    h_mm = max(float(storey_height_m), 0.1) * 1000.0

    num_risers = max(1, round(h_mm / max(target_riser_mm, 1.0)))
    riser = h_mm / num_risers
    going = max(_TWO_R_PLUS_G - 2.0 * riser, MIN_GOING_MM)
    num_treads = max(1, num_risers - 1)

    # Apply explicit overrides (engineer always wins).
    riser = float(overrides.get("riser", riser))
    going = float(overrides.get("going", overrides.get("tread", going)))
    waist_mm = float(overrides.get("waist", waist_mm))
    if "num_steps" in overrides:
        num_treads = int(overrides["num_steps"])

    flight_horizontal_mm = num_treads * going
    span_mm = flight_horizontal_mm + landing_mm
    if "span" in overrides:
        span_mm = float(overrides["span"])
    elif "L_plan_m" in overrides:
        span_mm = float(overrides["L_plan_m"]) * 1000.0

    return {
        "num_risers": num_risers,
        "riser": round(riser, 2),
        "going": round(going, 2),
        "num_steps": num_treads,
        "flight_horizontal_mm": round(flight_horizontal_mm, 1),
        "landing_mm": landing_mm,
        "span_mm": round(span_mm, 1),
        "L_plan_m": round(span_mm / 1000.0, 3),
        "waist_mm": waist_mm,
    }

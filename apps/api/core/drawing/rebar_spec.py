"""
core/drawing/rebar_spec.py
==========================
Parse human-readable reinforcement specification strings into the numeric
fields the drawing generators need.

Wall and footing designs express their steel as the string produced by
``select_slab_reinforcement`` / ``select_reinforcement`` —
``"H{dia} @ {spacing} c/c"`` (e.g. ``"H12 @ 150 c/c"``).  A count-prefixed
variant (``"10H16 @ 150 c/c"``) is also tolerated for robustness.

The generators draw bars from the parsed ``diameter``/``spacing``; the optional
``count`` is used when an explicit bar count is given rather than a spacing.
"""

from __future__ import annotations

import re

# ``[<count>]H<dia> [@ <spacing> [c/c]]`` — case-insensitive, whitespace-tolerant.
_BAR_SPEC_RE = re.compile(
    r"""
    ^\s*
    (?:(?P<count>\d+)\s*)?          # optional leading bar count
    [HTRY]?                          # optional bar-type prefix (H/T/R/Y)
    (?P<diameter>\d+(?:\.\d+)?)      # nominal diameter (mm)
    (?:\s*@\s*(?P<spacing>\d+(?:\.\d+)?))?   # optional centre spacing (mm)
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Fallbacks when the string is empty / unparseable, matching the conservative
# defaults the other generators already use.
_DEFAULT_DIAMETER = 12.0
_DEFAULT_SPACING = 200.0


def parse_bar_spec(spec: str | None) -> dict:
    """
    Parse a reinforcement specification string.

    Parameters
    ----------
    spec : str | None
        Reinforcement description, e.g. ``"H12 @ 150 c/c"`` or ``"10H16 @ 150 c/c"``.
        ``None``/empty/unrecognised input yields sensible defaults.

    Returns
    -------
    dict
        ``{"count": int | None, "diameter": float, "spacing": float | None}``.
        ``diameter`` always populated; ``spacing`` is ``None`` only when a count
        was given without a spacing.
    """
    if not spec or not isinstance(spec, str):
        return {"count": None, "diameter": _DEFAULT_DIAMETER, "spacing": _DEFAULT_SPACING}

    match = _BAR_SPEC_RE.match(spec)
    if not match:
        return {"count": None, "diameter": _DEFAULT_DIAMETER, "spacing": _DEFAULT_SPACING}

    diameter = float(match.group("diameter"))
    if diameter <= 0:
        diameter = _DEFAULT_DIAMETER

    count = int(match.group("count")) if match.group("count") else None
    spacing_raw = match.group("spacing")
    spacing = float(spacing_raw) if spacing_raw else (None if count else _DEFAULT_SPACING)

    return {"count": count, "diameter": diameter, "spacing": spacing}


def bar_count_for_width(spec: dict, width: float) -> int:
    """
    Resolve how many bars to draw across ``width`` from a parsed spec.

    Uses the explicit count when present, otherwise derives a count from the
    centre spacing (the same idiom the staircase generator uses).  Always
    returns at least two bars so a section/elevation never renders empty.
    """
    count = spec.get("count")
    if count and count > 0:
        return max(2, int(count))
    spacing = spec.get("spacing") or _DEFAULT_SPACING
    return max(2, int(width // max(spacing, 1.0)) + 1)

"""
services/agents/drawing_generators/__init__.py
===============================================
Drawing command generator package.

Each generator class translates a designed member dict into a list of
structured draw commands that the HTML5 Canvas panel interprets.

This is **deterministic code, not AI** — the Drafting Agent only orchestrates
which generator to call.  The generators themselves apply fixed geometric rules.

Draw Command Format
-------------------
Every command is a plain dict consumed by the frontend canvas renderer:

{
    "type": "rect" | "circle" | "line" | "text" | "dimension" | "polyline",
    "style": "structural_outline" | "rebar" | "link" | "cover_line" |
              "dimension_line" | "annotation",
    "label": str | None,
    "mark":  str | None,
    -- geometry fields per type --
}

Coordinate system
-----------------
- Origin (0, 0) is the **top-left** corner of each member's drawing viewport.
- x increases right, y increases down (standard Canvas convention).
- All coordinates are in **millimetres** (the frontend scales to screen pixels).
"""

from core.drawing.beam import BeamDrawingGenerator
from core.drawing.slab import SlabDrawingGenerator
from core.drawing.column import ColumnDrawingGenerator
from core.drawing.wall import WallDrawingGenerator
from core.drawing.footing import FootingDrawingGenerator
from core.drawing.staircase import StaircaseDrawingGenerator

# Registry: member_type → generator class
GENERATOR_REGISTRY: dict[str, type] = {
    "beam":           BeamDrawingGenerator,
    "slab_one_way":   SlabDrawingGenerator,
    "slab_two_way":   SlabDrawingGenerator,
    "slab_ribbed":    SlabDrawingGenerator,
    "slab_waffle":    SlabDrawingGenerator,
    "slab_flat":      SlabDrawingGenerator,
    "column":         ColumnDrawingGenerator,
    "wall":           WallDrawingGenerator,
    "footing_pad":    FootingDrawingGenerator,
    "staircase":      StaircaseDrawingGenerator,
}


def generate_drawing_commands(member: dict) -> dict:
    """
    Dispatch to the correct generator class and return a complete command set.

    Parameters
    ----------
    member : dict
        Designed member dict from the design API results.  Must contain at
        minimum:  ``member_id``, ``member_type``, ``geometry``,
        ``reinforcement``, ``design_code``.

    Returns
    -------
    dict
        ``{section, elevation, dimensions, bar_marks, annotations,
           canvas_bounds, scale}``

    Raises
    ------
    ValueError
        If ``member_type`` is not in the registry.
    """
    member_type: str = member.get("member_type", "")
    generator_cls = GENERATOR_REGISTRY.get(member_type)
    if generator_cls is None:
        raise ValueError(
            f"No drawing generator for member type '{member_type}'. "
            f"Valid types: {list(GENERATOR_REGISTRY)}"
        )
    generator = generator_cls(member)
    return {
        "section":       generator.draw_section(),
        "elevation":     generator.draw_elevation(),
        "dimensions":    generator.draw_dimensions(),
        "bar_marks":     generator.draw_bar_marks(),
        "annotations":   generator.draw_annotations(),
        "canvas_bounds": generator.canvas_bounds(),
        "scale":         generator.drawing_scale(),
    }


__all__ = [
    "BeamDrawingGenerator",
    "SlabDrawingGenerator",
    "ColumnDrawingGenerator",
    "WallDrawingGenerator",
    "FootingDrawingGenerator",
    "StaircaseDrawingGenerator",
    "GENERATOR_REGISTRY",
    "generate_drawing_commands",
]

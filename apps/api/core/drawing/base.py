"""
services/agents/drawing_generators/base.py
==========================================
Abstract base class for all structural detail drawing generators.

Every generator receives a designed member dict and produces five lists of
draw commands (section, elevation, dimensions, bar_marks, annotations) plus
canvas metadata.

Subclasses must implement:
- ``draw_section()``   : cross-section at critical position
- ``draw_elevation()`` : longitudinal elevation / plan as appropriate
- ``draw_dimensions()``: dimension lines and values
- ``draw_bar_marks()`` : bar mark leader labels
- ``draw_annotations()``: title block, notes, material properties
- ``canvas_bounds()``  : (width, height) in mm of the drawing viewport
- ``drawing_scale()``  : representative drawing scale (e.g. 20 for 1:20)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseDrawingGenerator(ABC):
    """
    Abstract base for all structural member drawing generators.

    Parameters
    ----------
    member : dict
        Designed member dict output from the design API.

    Attributes
    ----------
    member_id : str
        Member identifier.
    design_code : str
        Design code string (BS8110 or EC2).
    geometry : dict
        Member geometry dict from design results.
    reinforcement : dict
        Member reinforcement dict from design results.
    """

    def __init__(self, member: dict) -> None:
        self.member = member
        self.member_id: str = member.get("member_id", "?")
        self.design_code: str = member.get("design_code", "BS8110")
        self.geometry: dict = member.get("geometry", {})
        self.reinforcement: dict = member.get("reinforcement", {})
        self.design: dict = member.get("design", {})

    # ─── Required implementations ─────────────────────────────────────────────

    @abstractmethod
    def draw_section(self) -> list[dict]:
        """
        Return draw commands for the cross-section view.

        Returns
        -------
        list[dict]
            Ordered list of draw command dicts.
        """

    @abstractmethod
    def draw_elevation(self) -> list[dict]:
        """
        Return draw commands for the elevation or plan view.

        Returns
        -------
        list[dict]
            Ordered list of draw command dicts.
        """

    @abstractmethod
    def draw_dimensions(self) -> list[dict]:
        """
        Return dimension line draw commands.

        Returns
        -------
        list[dict]
            Ordered list of draw command dicts.
        """

    @abstractmethod
    def draw_bar_marks(self) -> list[dict]:
        """
        Return bar mark leader label commands.

        Returns
        -------
        list[dict]
            Ordered list of draw command dicts.
        """

    @abstractmethod
    def draw_annotations(self) -> list[dict]:
        """
        Return annotation commands (title block, material notes, code refs).

        Returns
        -------
        list[dict]
            Ordered list of draw command dicts.
        """

    @abstractmethod
    def canvas_bounds(self) -> dict:
        """
        Return the drawing viewport dimensions in mm.

        Returns
        -------
        dict
            ``{width: float, height: float}``
        """

    @abstractmethod
    def drawing_scale(self) -> int:
        """
        Return the representative drawing scale denominator (e.g. 20 for 1:20).

        Returns
        -------
        int
        """

    # ─── Shared factory methods ───────────────────────────────────────────────

    @staticmethod
    def rect(
        x: float, y: float, w: float, h: float, style: str,
        label: str | None = None, mark: str | None = None,
    ) -> dict[str, Any]:
        """
        Build a rectangle draw command.

        Parameters
        ----------
        x, y : float    Top-left corner in mm.
        w, h : float    Width and height in mm.
        style : str     CSS-style class name for the renderer.
        label : str     Optional text label.
        mark : str      Optional bar mark reference.

        Returns
        -------
        dict
        """
        return {"type": "rect", "x": x, "y": y, "width": w, "height": h,
                "style": style, "label": label, "mark": mark}

    @staticmethod
    def circle(
        cx: float, cy: float, r: float, style: str,
        label: str | None = None, mark: str | None = None,
    ) -> dict[str, Any]:
        """
        Build a circle draw command (used for rebar dots in section views).

        Parameters
        ----------
        cx, cy : float  Centre coordinates in mm.
        r : float       Radius in mm.
        style : str     CSS-style class name.
        label : str     Optional label.
        mark : str      Optional bar mark.

        Returns
        -------
        dict
        """
        return {"type": "circle", "cx": cx, "cy": cy, "r": r,
                "style": style, "label": label, "mark": mark}

    @staticmethod
    def line(
        x1: float, y1: float, x2: float, y2: float, style: str,
        label: str | None = None, mark: str | None = None,
        diameter: float | None = None,
    ) -> dict[str, Any]:
        """
        Build a line draw command (used for rebar in elevation views).

        Parameters
        ----------
        x1, y1 : float  Start point in mm.
        x2, y2 : float  End point in mm.
        style : str     CSS-style class name.
        label : str     Optional label.
        mark : str      Optional bar mark.
        diameter : float  Bar diameter in mm (used to set line weight).

        Returns
        -------
        dict
        """
        return {"type": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "style": style, "label": label, "mark": mark, "diameter": diameter}

    @staticmethod
    def dimension(
        axis: str, value: float, label: str,
        x: float = 0, y: float = 0,
    ) -> dict[str, Any]:
        """
        Build a dimension line command.

        Parameters
        ----------
        axis : str      "horizontal" or "vertical".
        value : float   Dimension value in mm.
        label : str     Text to display (e.g. "b = 300").
        x, y : float    Anchor point for the dimension line start.

        Returns
        -------
        dict
        """
        return {"type": "dimension", "axis": axis, "value": value,
                "label": label, "x": x, "y": y}

    @staticmethod
    def text(
        content: str, x: float, y: float, style: str = "annotation",
    ) -> dict[str, Any]:
        """
        Build a text draw command.

        Parameters
        ----------
        content : str   Text string.
        x, y : float    Position in mm.
        style : str     CSS-style class name.

        Returns
        -------
        dict
        """
        return {"type": "text", "text": content, "x": x, "y": y, "style": style}

    # ─── Common bar-position helpers ──────────────────────────────────────────

    def _bar_x_positions(
        self, count: int, b: float, cover: float, bar_dia: float
    ) -> list[float]:
        """
        Compute evenly-spaced bar x-coordinates within a section width.

        Parameters
        ----------
        count : int     Number of bars.
        b : float       Section width in mm.
        cover : float   Nominal cover in mm.
        bar_dia : float Bar diameter in mm.

        Returns
        -------
        list[float]
            x-coordinate of each bar centre.
        """
        if count == 1:
            return [b / 2]
        inner_width = b - 2 * cover - bar_dia
        spacing = inner_width / (count - 1)
        start = cover + bar_dia / 2
        return [start + i * spacing for i in range(count)]

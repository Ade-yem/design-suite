"""
services/agents/drawing_generators/beam.py
==========================================
Drawing command generator for rectangular RC beam members.

Produces:
- Section    : cross-section with tension/compression bars and link
- Elevation  : longitudinal elevation with curtailment zones
- Dimensions : b, h, cover dimension lines
- Bar marks  : count-diameter-mark annotations
- Annotations: title block with material properties

Coordinate origin: top-left of the section viewport.
All coordinates in millimetres.
"""

from __future__ import annotations

from core.drawing.base import BaseDrawingGenerator

# Section viewport padding (mm around the section outline)
_PAD = 50


class BeamDrawingGenerator(BaseDrawingGenerator):
    """
    Drawing generator for a rectangular RC beam section and elevation.

    Parameters
    ----------
    member : dict
        Designed beam member dict.  Expected keys:
        ``geometry.width_mm``, ``geometry.depth_mm``,
        ``design.cover_mm``, ``design.effective_depth_mm``,
        ``reinforcement.main_bars`` (list),
        ``reinforcement.links`` (list),
        ``design.span_zones`` (list).
    """

    def __init__(self, member: dict) -> None:
        super().__init__(member)
        geo = self.geometry
        des = self.design
        reo = self.reinforcement

        self.b: float = geo.get("width_mm", 300)
        self.h: float = geo.get("depth_mm", 500)
        self.cover: float = des.get("cover_mm", 35)
        self.d: float = des.get("effective_depth_mm", self.h - self.cover - 10)
        self.L: float = geo.get("span_mm", 5000)

        self.main_bars: list[dict] = reo.get("main_bars", [])
        self.links: list[dict] = reo.get("links", [])
        self.span_zones: list[dict] = des.get("span_zones", [])

        # Split main bars into top / bottom by position flag
        self.bottom_bars = [bar for bar in self.main_bars if bar.get("position") != "top"]
        self.top_bars    = [bar for bar in self.main_bars if bar.get("position") == "top"]

    # ─── Section ──────────────────────────────────────────────────────────────

    def draw_section(self) -> list[dict]:
        """
        Draw the beam cross-section.

        Includes:
        - Outer outline (concrete boundary)
        - Cover rectangle (dashed)
        - Bottom tension bars (filled circles)
        - Top compression / hanger bars
        - Link rectangle

        Returns
        -------
        list[dict]
        """
        cmds = []
        ox, oy = _PAD, _PAD  # Section origin with padding

        # Outer concrete outline
        cmds.append(self.rect(ox, oy, self.b, self.h, "structural_outline"))

        # Cover rectangle
        cmds.append(self.rect(
            ox + self.cover, oy + self.cover,
            self.b - 2 * self.cover, self.h - 2 * self.cover,
            "cover_line",
        ))

        # Bottom tension bars
        n_bot = sum(bar.get("count", 0) for bar in self.bottom_bars)
        if n_bot:
            bar_dia = self.bottom_bars[0].get("diameter", 16) if self.bottom_bars else 16
            r = bar_dia / 2
            xs = self._bar_x_positions(n_bot, self.b, self.cover, bar_dia)
            cy = oy + self.h - self.cover - r
            mark = self.bottom_bars[0].get("mark", "") if self.bottom_bars else ""
            for x in xs:
                cmds.append(self.circle(ox + x, cy, r, "rebar", mark=mark))

        # Top bars (hanger / compression)
        n_top = sum(bar.get("count", 0) for bar in self.top_bars)
        if n_top:
            bar_dia = self.top_bars[0].get("diameter", 12) if self.top_bars else 12
            r = bar_dia / 2
            xs = self._bar_x_positions(n_top, self.b, self.cover, bar_dia)
            cy = oy + self.cover + r
            mark = self.top_bars[0].get("mark", "") if self.top_bars else ""
            for x in xs:
                cmds.append(self.circle(ox + x, cy, r, "rebar", mark=mark))

        # Link rectangle
        if self.links:
            lnk = self.links[0]
            ld = lnk.get("diameter", 8)
            cmds.append(self.rect(
                ox + self.cover, oy + self.cover,
                self.b - 2 * self.cover, self.h - 2 * self.cover,
                "link",
                label=f"R{ld}@{lnk.get('spacing', '200')}",
                mark=lnk.get("mark", ""),
            ))

        return cmds

    # ─── Elevation ────────────────────────────────────────────────────────────

    def draw_elevation(self) -> list[dict]:
        """
        Draw the beam longitudinal elevation showing bar curtailment zones.

        Returns
        -------
        list[dict]
        """
        cmds = []
        oy_bot = _PAD + self.h - self.cover  # y of bottom rebar line
        oy_top = _PAD + self.cover           # y of top rebar line

        for zone in self.span_zones:
            x1 = zone.get("start_x", 0) + _PAD
            x2 = zone.get("end_x", self.L) + _PAD
            pos = zone.get("position", "bottom")
            y = oy_bot if pos == "bottom" else oy_top
            cmds.append(self.line(
                x1, y, x2, y, "rebar",
                label=zone.get("bar_mark", ""),
                mark=zone.get("bar_mark", ""),
                diameter=zone.get("diameter", 16),
            ))

        # Beam outline
        cmds.insert(0, self.rect(_PAD, _PAD, self.L, self.h, "structural_outline"))
        return cmds

    # ─── Dimensions ───────────────────────────────────────────────────────────

    def draw_dimensions(self) -> list[dict]:
        """
        Return dimension lines for b, h, and cover.

        Returns
        -------
        list[dict]
        """
        return [
            self.dimension("horizontal", self.b, f"b = {self.b:.0f}", x=_PAD, y=_PAD + self.h + 20),
            self.dimension("vertical",   self.h, f"h = {self.h:.0f}", x=_PAD - 30, y=_PAD),
            self.dimension("horizontal", self.cover, f"c = {self.cover:.0f}", x=_PAD, y=_PAD + 5),
        ]

    # ─── Bar marks ────────────────────────────────────────────────────────────

    def draw_bar_marks(self) -> list[dict]:
        """
        Return bar mark label commands for all main bars.

        Returns
        -------
        list[dict]
        """
        cmds = []
        x_label = _PAD + self.b + 10
        for i, bar in enumerate(self.main_bars):
            count = bar.get("count", 0)
            dia   = bar.get("diameter", 16)
            mark  = bar.get("mark", f"01{i+1}")
            pos   = bar.get("position", "bottom")
            y = _PAD + (self.h - self.cover) if pos != "top" else _PAD + self.cover
            cmds.append(self.text(
                f"{count}T{dia}-{mark}", x_label, y + i * 20, "bar_mark"
            ))
        return cmds

    # ─── Annotations ──────────────────────────────────────────────────────────

    def draw_annotations(self) -> list[dict]:
        """
        Return title block and material property annotations.

        Returns
        -------
        list[dict]
        """
        fcu = self.design.get("fcu_MPa", self.design.get("fck_MPa", 30))
        fy  = self.design.get("fy_MPa", 500)
        return [
            self.text(f"BEAM {self.member_id} — SECTION", _PAD, _PAD - 30, "title"),
            self.text(
                f"fcu = {fcu} MPa  |  fy = {fy} MPa  |  Cover = {self.cover} mm",
                _PAD, _PAD - 15, "subtitle",
            ),
            self.text(f"Code: {self.design_code}", _PAD, _PAD - 5, "subtitle"),
        ]

    # ─── Canvas metadata ──────────────────────────────────────────────────────

    def canvas_bounds(self) -> dict:
        """Return section viewport dimensions (width × height in mm)."""
        return {"width": self.b + 2 * _PAD + 120, "height": self.h + 2 * _PAD + 60}

    def drawing_scale(self) -> int:
        """Return 1:10 for typical beam sections."""
        return 10

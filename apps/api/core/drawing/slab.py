"""
services/agents/drawing_generators/slab.py
==========================================
Drawing command generator for Slab members.

Produces:
- Section    : cross-section per unit strip
- Plan       : plan view showing bar spacing and direction
- Dimensions : h, cover, span
- Bar marks  : count-diameter-spacing annotations
- Annotations: title block with material properties
"""

from __future__ import annotations

from core.drawing.base import BaseDrawingGenerator

_PAD = 50

class SlabDrawingGenerator(BaseDrawingGenerator):
    def __init__(self, member: dict) -> None:
        super().__init__(member)
        geo = self.geometry
        des = self.design
        reo = self.reinforcement

        self.h: float = geo.get("depth_mm", 200)
        self.cover: float = des.get("cover_mm", 25)
        self.L: float = geo.get("span_mm", 4000)
        self.width: float = 1000  # standard 1m strip

        self.main_bars: list[dict] = reo.get("main_bars", [])
        self.distribution_bars: list[dict] = reo.get("distribution_bars", [])

    def draw_section(self) -> list[dict]:
        cmds = []
        ox, oy = _PAD, _PAD

        # Outline (1m strip)
        cmds.append(self.rect(ox, oy, self.width, self.h, "structural_outline"))

        # Main reinforcement (bottom)
        if self.main_bars:
            bar = self.main_bars[0]
            dia = bar.get("diameter", 12)
            spacing = bar.get("spacing", 200)
            commands = int(self.width // spacing) + 1
            xs = [i * spacing for i in range(commands)]
            cy = oy + self.h - self.cover - dia / 2
            for x in xs:
                if x <= self.width:
                    cmds.append(self.circle(ox + x, cy, dia / 2, "rebar", mark=bar.get("mark", "")))
        
        # Distribution bars (perpendicular, shown as line)
        if self.distribution_bars:
            dbar = self.distribution_bars[0]
            cmds.append(self.line(
                 ox, oy + self.h - self.cover - 15, 
                 ox + self.width, oy + self.h - self.cover - 15,
                 "rebar", label=dbar.get("mark", ""), diameter=dbar.get("diameter", 10)
            ))

        return cmds

    def draw_elevation(self) -> list[dict]:
        cmds = []
        # Plan view simplified
        cmds.append(self.rect(_PAD, _PAD, self.L, self.width, "structural_outline"))
        return cmds

    def draw_dimensions(self) -> list[dict]:
        return [
            self.dimension("vertical", self.h, f"h = {self.h:.0f}", x=_PAD - 30, y=_PAD),
        ]

    def draw_bar_marks(self) -> list[dict]:
        cmds = []
        if self.main_bars:
            bar = self.main_bars[0]
            cmds.append(self.text(
                f"T{bar.get('diameter', 12)}@{bar.get('spacing', 200)} B1",
                _PAD + 10, _PAD + self.h + 20, "bar_mark"
            ))
        return cmds

    def draw_annotations(self) -> list[dict]:
        fcu = self.design.get("fcu_MPa", self.design.get("fck_MPa", 30))
        return [
            self.text(f"SLAB {self.member_id} — SECTION", _PAD, _PAD - 30, "title"),
            self.text(f"fcu = {fcu} MPa | Cover = {self.cover} mm", _PAD, _PAD - 15, "subtitle"),
        ]

    def canvas_bounds(self) -> dict:
        return {"width": self.width + 2 * _PAD + 50, "height": self.h + 2 * _PAD + 60}

    def drawing_scale(self) -> int:
        return 20

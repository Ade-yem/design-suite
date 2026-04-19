"""
services/agents/drawing_generators/column.py
============================================
Drawing command generator for Column members.
"""
from core.drawing.base import BaseDrawingGenerator
_PAD = 50

class ColumnDrawingGenerator(BaseDrawingGenerator):
    def __init__(self, member: dict) -> None:
        super().__init__(member)
        self.b = self.geometry.get("width_mm", 300)
        self.h = self.geometry.get("depth_mm", 300)
        self.L = self.geometry.get("height_mm", 3000)
        self.cover = self.design.get("cover_mm", 35)
        self.main_bars = self.reinforcement.get("main_bars", [])
        self.links = self.reinforcement.get("links", [])

    def draw_section(self) -> list[dict]:
        cmds = [self.rect(_PAD, _PAD, self.b, self.h, "structural_outline")]
        cmds.append(self.rect(_PAD+self.cover, _PAD+self.cover, self.b-2*self.cover, self.h-2*self.cover, "link"))
        # Simplified: just showing dots at corners for now
        bx = [_PAD+self.cover, _PAD+self.b-self.cover]
        by = [_PAD+self.cover, _PAD+self.h-self.cover]
        for x in bx:
            for y in by:
                cmds.append(self.circle(x, y, 8, "rebar"))
        return cmds

    def draw_elevation(self) -> list[dict]:
        return [self.rect(_PAD, _PAD, self.b, self.L, "structural_outline")]

    def draw_dimensions(self) -> list[dict]:
        return [self.dimension("horizontal", self.b, f"b={self.b}", _PAD, _PAD+self.h+20)]

    def draw_bar_marks(self) -> list[dict]:
        if not self.main_bars: return []
        bar = self.main_bars[0]
        return [self.text(f"{bar.get('count',4)}T{bar.get('diameter',16)}", _PAD+self.b+10, _PAD+self.h/2, "bar_mark")]

    def draw_annotations(self) -> list[dict]:
        return [self.text(f"COLUMN {self.member_id}", _PAD, _PAD-20, "title")]

    def canvas_bounds(self) -> dict:
        return {"width": self.b + 2*_PAD + 100, "height": self.h + 2*_PAD + 50}

    def drawing_scale(self) -> int:
        return 10

"""
services/agents/drawing_generators/footing.py
============================================
Drawing command generator for Footing members.
"""
from core.drawing.base import BaseDrawingGenerator
_PAD = 50

class FootingDrawingGenerator(BaseDrawingGenerator):
    def __init__(self, member: dict) -> None:
        super().__init__(member)
    def draw_section(self) -> list[dict]: return []
    def draw_elevation(self) -> list[dict]: return []
    def draw_dimensions(self) -> list[dict]: return []
    def draw_bar_marks(self) -> list[dict]: return []
    def draw_annotations(self) -> list[dict]: return []
    def canvas_bounds(self) -> dict: return {"width": 500, "height": 500}
    def drawing_scale(self) -> int: return 20

"""
core/drawing/footing.py
=======================
Drawing command generator for reinforced concrete pad-footing members.

Produces a real detail (previously a stub returning empty lists):
- Section    : vertical section through the depth (length lx × depth h) with the
               column stub and the bottom-face bars (x-direction) as dots.
- Elevation  : the foundation plan (lx × ly) showing the reinforcement mat —
               x-direction and y-direction bars — and the centred column.
- Dimensions : lx, ly, depth, cover.
- Bar marks  : x / y reinforcement callouts.
- Annotations: title block with materials, bearing pressure and status.

The designed footing member is the **flat** output of ``design_member`` for a
footing (``design_pad_footing`` result plus ``member_id``/``member_type``/
``design_code``).  Its steel is given as the strings ``reinforcement_x`` /
``reinforcement_y`` (e.g. ``"H16 @ 150 c/c"``).  Section dimensions are not on
the flat dict today, so they are read defensively from ``geometry`` / ``design``
/ ``meta`` with sensible fallbacks — like the staircase generator — so a footing
always renders.
"""

from __future__ import annotations

from core.drawing.base import BaseDrawingGenerator
from core.drawing.rebar_spec import bar_count_for_width, parse_bar_spec

_PAD = 50


class FootingDrawingGenerator(BaseDrawingGenerator):
    """Drawing generator for an RC pad-footing section and plan."""

    def __init__(self, member: dict) -> None:
        super().__init__(member)
        geo = self.geometry
        des = self.design
        meta = member.get("meta", {}) or {}

        def _g(*keys: str, default: float) -> float:
            for src in (member, geo, des, meta):
                for k in keys:
                    if isinstance(src, dict) and src.get(k) is not None:
                        try:
                            return float(src[k])
                        except (TypeError, ValueError):
                            continue
            return default

        self.lx: float = _g("lx", "lx_mm", "B_mm", default=1500.0)
        self.ly: float = _g("ly", "ly_mm", "L_mm", default=1500.0)
        self.h: float = _g("h", "h_footing_mm", "depth_mm", default=500.0)
        self.cover: float = _g("cover_mm", "cover", default=50.0)
        self.cx: float = _g("column_cx", "c1", default=300.0)
        self.cy: float = _g("column_cy", "c2", default=300.0)

        self.x_spec: dict = parse_bar_spec(member.get("reinforcement_x"))
        self.y_spec: dict = parse_bar_spec(member.get("reinforcement_y"))

        self.x_label: str = str(member.get("reinforcement_x") or "")
        self.y_label: str = str(member.get("reinforcement_y") or "")

    # ── views ──────────────────────────────────────────────────────────────────
    def draw_section(self) -> list[dict]:
        """Vertical section through depth: pad outline, column stub, bottom x-bars."""
        cmds: list[dict] = []
        ox, oy = _PAD, _PAD

        # Pad outline (length lx across x, depth h down y).
        cmds.append(self.rect(ox, oy, self.lx, self.h, "structural_outline"))

        # Column stub rising from the centre of the pad top.
        col_h = min(self.h * 0.6, 300.0)
        cmds.append(self.rect(ox + (self.lx - self.cx) / 2, oy - col_h, self.cx, col_h,
                              "structural_outline", label="column"))

        # Bottom-face bars (x-direction) as dots near the soffit.
        dia = self.x_spec["diameter"]
        r = dia / 2
        count = bar_count_for_width(self.x_spec, self.lx)
        cy = oy + self.h - self.cover - r
        for x in self._bar_x_positions(count, self.lx, self.cover, dia):
            cmds.append(self.circle(ox + x, cy, r, "rebar", mark=self.x_label))
        return cmds

    def draw_elevation(self) -> list[dict]:
        """Foundation plan (lx × ly): reinforcement mat + centred column."""
        cmds: list[dict] = [self.rect(_PAD, _PAD, self.lx, self.ly, "structural_outline")]

        # Centred column footprint.
        cmds.append(self.rect(_PAD + (self.lx - self.cx) / 2, _PAD + (self.ly - self.cy) / 2,
                              self.cx, self.cy, "cover_line", label="column"))

        # X-direction bars run along x, distributed down y.
        xdia = self.x_spec["diameter"]
        xcount = bar_count_for_width(self.x_spec, self.ly)
        for y in self._bar_x_positions(xcount, self.ly, self.cover, xdia):
            cmds.append(self.line(_PAD + self.cover, _PAD + y, _PAD + self.lx - self.cover, _PAD + y,
                                  "rebar", diameter=xdia, mark=self.x_label))

        # Y-direction bars run along y, distributed across x.
        ydia = self.y_spec["diameter"]
        ycount = bar_count_for_width(self.y_spec, self.lx)
        for x in self._bar_x_positions(ycount, self.lx, self.cover, ydia):
            cmds.append(self.line(_PAD + x, _PAD + self.cover, _PAD + x, _PAD + self.ly - self.cover,
                                  "rebar", diameter=ydia, mark=self.y_label))
        return cmds

    def draw_dimensions(self) -> list[dict]:
        return [
            self.dimension("horizontal", self.lx, f"lx = {self.lx:.0f}", x=_PAD, y=_PAD + self.ly + 20),
            self.dimension("vertical", self.ly, f"ly = {self.ly:.0f}", x=_PAD - 30, y=_PAD),
            self.dimension("vertical", self.h, f"h = {self.h:.0f}", x=_PAD - 15, y=_PAD),
            self.dimension("horizontal", self.cover, f"c = {self.cover:.0f}", x=_PAD, y=_PAD + 5),
        ]

    def draw_bar_marks(self) -> list[dict]:
        x_label = _PAD + self.lx + 10
        return [
            self.text(f"{self.x_label or 'x steel'} (x, bottom)", x_label, _PAD + 20, "bar_mark"),
            self.text(f"{self.y_label or 'y steel'} (y, bottom)", x_label, _PAD + 40, "bar_mark"),
        ]

    def draw_annotations(self) -> list[dict]:
        fcu = self.member.get("fcu_MPa") or self.design.get("fcu_MPa") or self.design.get("fck_MPa") or 30
        fy = self.member.get("fy_MPa") or self.design.get("fy_MPa") or 460
        q_max = self.member.get("q_max_kNm2")
        status = self.member.get("status") or ""
        subtitle = f"fcu = {fcu} MPa  |  fy = {fy} MPa  |  Cover = {self.cover:.0f} mm"
        if q_max is not None:
            subtitle += f"  |  q_max = {q_max} kN/m²"
        if status:
            subtitle += f"  |  {status}"
        return [
            self.text(f"FOOTING {self.member_id} — SECTION & PLAN", _PAD, _PAD - 30, "title"),
            self.text(subtitle, _PAD, _PAD - 15, "subtitle"),
            self.text(f"Code: {self.design_code}", _PAD, _PAD - 5, "subtitle"),
        ]

    def canvas_bounds(self) -> dict:
        width = self.lx + 2 * _PAD + 160
        height = self.ly + 2 * _PAD + 60
        return {"width": max(width, 500), "height": max(height, 500)}

    def drawing_scale(self) -> int:
        return 25

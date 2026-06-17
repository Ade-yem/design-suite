"""
core/drawing/wall.py
====================
Drawing command generator for reinforced concrete wall members.

Produces a real detail (previously a stub returning empty lists):
- Section    : horizontal cut through the wall thickness over a representative
               length strip, with vertical bars drawn near each face.
- Elevation  : the wall face (length × height) with vertical and horizontal bars.
- Dimensions : length, height, thickness, cover.
- Bar marks  : vertical / horizontal steel callouts.
- Annotations: title block with materials and slenderness.

The designed wall member is the **flat** output of ``design_member`` for a wall
(``design_reinforced_wall`` result plus ``member_id``/``member_type``/``design_code``).
Its steel is given as the strings ``vertical_steel`` / ``horizontal_steel``
(e.g. ``"H12 @ 150 c/c"``).  Section dimensions are not on the flat dict today,
so they are read defensively from ``geometry`` / ``design`` / ``meta`` with
sensible fallbacks — exactly like the staircase generator — so a wall always
renders.
"""

from __future__ import annotations

from core.drawing.base import BaseDrawingGenerator
from core.drawing.rebar_spec import bar_count_for_width, parse_bar_spec

_PAD = 50

# Representative length of wall shown in the horizontal section (mm).
_SECTION_STRIP = 1000.0


class WallDrawingGenerator(BaseDrawingGenerator):
    """Drawing generator for an RC wall section and elevation."""

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

        self.thickness: float = _g("h", "h_wall_mm", "thickness_mm", "width_mm", default=200.0)
        self.l_w: float = _g("l_w", "l_w_mm", "length_mm", "span_mm", default=3000.0)
        self.height: float = _g("l_e", "l_e_mm", "clear_height_mm", "height_mm", default=3000.0)
        self.cover: float = _g("cover_mm", "cover", default=25.0)

        self.vert_spec: dict = parse_bar_spec(member.get("vertical_steel"))
        self.horiz_spec: dict = parse_bar_spec(member.get("horizontal_steel"))

        self.vert_label: str = str(member.get("vertical_steel") or "")
        self.horiz_label: str = str(member.get("horizontal_steel") or "")

    # ── views ──────────────────────────────────────────────────────────────────
    def draw_section(self) -> list[dict]:
        """Horizontal section: thickness × representative length strip, bars at each face."""
        cmds: list[dict] = []
        strip = min(self.l_w, _SECTION_STRIP)
        ox, oy = _PAD, _PAD

        # Concrete outline (length across x, thickness down y) and cover line.
        cmds.append(self.rect(ox, oy, strip, self.thickness, "structural_outline"))
        cmds.append(self.rect(ox + self.cover, oy + self.cover,
                              strip - 2 * self.cover, self.thickness - 2 * self.cover,
                              "cover_line"))

        # Vertical bars appear as dots on both faces of the cut.
        dia = self.vert_spec["diameter"]
        r = dia / 2
        count = bar_count_for_width(self.vert_spec, strip)
        xs = self._bar_x_positions(count, strip, self.cover, dia)
        near = oy + self.cover + r
        far = oy + self.thickness - self.cover - r
        for x in xs:
            cmds.append(self.circle(ox + x, near, r, "rebar", mark=self.vert_label))
            cmds.append(self.circle(ox + x, far, r, "rebar", mark=self.vert_label))
        return cmds

    def draw_elevation(self) -> list[dict]:
        """Wall face (length × height) with vertical and horizontal bars."""
        cmds: list[dict] = [self.rect(_PAD, _PAD, self.l_w, self.height, "structural_outline")]

        # Vertical bars across the length.
        vdia = self.vert_spec["diameter"]
        vcount = bar_count_for_width(self.vert_spec, self.l_w)
        for x in self._bar_x_positions(vcount, self.l_w, self.cover, vdia):
            cmds.append(self.line(_PAD + x, _PAD + self.cover, _PAD + x, _PAD + self.height - self.cover,
                                  "rebar", diameter=vdia, mark=self.vert_label))

        # Horizontal bars up the height.
        hdia = self.horiz_spec["diameter"]
        hcount = bar_count_for_width(self.horiz_spec, self.height)
        for y in self._bar_x_positions(hcount, self.height, self.cover, hdia):
            cmds.append(self.line(_PAD + self.cover, _PAD + y, _PAD + self.l_w - self.cover, _PAD + y,
                                  "rebar", diameter=hdia, mark=self.horiz_label))
        return cmds

    def draw_dimensions(self) -> list[dict]:
        return [
            self.dimension("horizontal", self.l_w, f"l_w = {self.l_w:.0f}", x=_PAD, y=_PAD + self.height + 20),
            self.dimension("vertical", self.height, f"H = {self.height:.0f}", x=_PAD - 30, y=_PAD),
            self.dimension("horizontal", self.thickness, f"t = {self.thickness:.0f}", x=_PAD, y=_PAD - 15),
            self.dimension("horizontal", self.cover, f"c = {self.cover:.0f}", x=_PAD, y=_PAD + 5),
        ]

    def draw_bar_marks(self) -> list[dict]:
        x_label = _PAD + self.l_w + 10
        return [
            self.text(f"{self.vert_label or 'vert. steel'} (vertical)", x_label, _PAD + 20, "bar_mark"),
            self.text(f"{self.horiz_label or 'horiz. steel'} (horizontal)", x_label, _PAD + 40, "bar_mark"),
        ]

    def draw_annotations(self) -> list[dict]:
        fcu = self.member.get("fcu_MPa") or self.design.get("fcu_MPa") or self.design.get("fck_MPa") or 30
        fy = self.member.get("fy_MPa") or self.design.get("fy_MPa") or 500
        slenderness = self.member.get("slenderness") or self.design.get("slenderness") or ""
        subtitle = f"fcu = {fcu} MPa  |  fy = {fy} MPa  |  Cover = {self.cover:.0f} mm"
        if slenderness:
            subtitle += f"  |  {slenderness}"
        return [
            self.text(f"WALL {self.member_id} — SECTION & ELEVATION", _PAD, _PAD - 30, "title"),
            self.text(subtitle, _PAD, _PAD - 15, "subtitle"),
            self.text(f"Code: {self.design_code}", _PAD, _PAD - 5, "subtitle"),
        ]

    def canvas_bounds(self) -> dict:
        width = self.l_w + 2 * _PAD + 160
        height = self.height + 2 * _PAD + 60
        return {"width": max(width, 500), "height": max(height, 500)}

    def drawing_scale(self) -> int:
        return 20

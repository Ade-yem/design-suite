"""
core/drawing/staircase.py
=========================
Drawing command generator for Staircase members.

Produces a real flight drawing (previously a stub returning empty lists):
- Section    : transverse cross-section of the waist slab with main steel.
- Elevation  : the longitudinal flight profile (treads + risers), the inclined
               waist soffit, the main tension bars following the soffit, and the
               landing.
- Dimensions : waist, riser, going, span.
- Bar marks  : main / distribution bar callouts.
- Annotations: title block with materials.

Geometry is read defensively from the designed member dict (``geometry`` /
``design`` / ``reinforcement``) with sensible fallbacks, matching the other
generators, so a flight always renders.
"""

from __future__ import annotations

from core.drawing.base import BaseDrawingGenerator

_PAD = 50


class StaircaseDrawingGenerator(BaseDrawingGenerator):
    def __init__(self, member: dict) -> None:
        super().__init__(member)
        geo = self.geometry
        des = self.design
        reo = self.reinforcement

        def _g(*keys: str, default: float) -> float:
            for src in (geo, des, member.get("meta", {}) or {}):
                for k in keys:
                    if src.get(k) is not None:
                        return float(src[k])
            return default

        self.waist: float = _g("waist", "waist_mm", "depth_mm", default=150.0)
        self.riser: float = _g("riser", "riser_mm", "R", default=175.0)
        self.going: float = _g("going", "tread", "tread_mm", "G", default=250.0)
        self.span: float = _g("span", "span_mm", "L_plan", default=4000.0)
        self.width: float = _g("width", "width_mm", default=1000.0)
        self.cover: float = _g("cover_mm", "cover", default=25.0)
        self.num_steps: int = int(_g("num_steps", default=max(1, round(self.span / max(self.going, 1)))))
        self.landing: float = _g("landing_mm", default=1000.0)

        self.main_bars: list[dict] = reo.get("main_bars", []) or []
        self.distribution_bars: list[dict] = reo.get("distribution_bars", []) or []

    # ── helpers ───────────────────────────────────────────────────────────────
    def _main_dia(self) -> float:
        if self.main_bars:
            return float(self.main_bars[0].get("diameter", 12))
        return 12.0

    def _main_mark(self) -> str:
        if self.main_bars:
            return str(self.main_bars[0].get("mark", ""))
        return ""

    # ── views ─────────────────────────────────────────────────────────────────
    def draw_section(self) -> list[dict]:
        """Transverse section of the waist slab (width × waist) with main steel."""
        cmds: list[dict] = []
        ox, oy = _PAD, _PAD
        cmds.append(self.rect(ox, oy, self.width, self.waist, "structural_outline"))

        dia = self._main_dia()
        spacing = float(self.main_bars[0].get("spacing", 150)) if self.main_bars else 150.0
        count = max(2, int(self.width // spacing) + 1)
        cy = oy + self.waist - self.cover - dia / 2
        for x in self._bar_x_positions(count, self.width, self.cover, dia):
            cmds.append(self.circle(ox + x, cy, dia / 2, "rebar", mark=self._main_mark()))

        # Distribution steel, shown as a longitudinal line near the soffit.
        ddia = float(self.distribution_bars[0].get("diameter", 10)) if self.distribution_bars else 10.0
        cmds.append(
            self.line(ox, oy + self.cover + ddia / 2, ox + self.width, oy + self.cover + ddia / 2,
                      "rebar", diameter=ddia,
                      label=(self.distribution_bars[0].get("mark", "") if self.distribution_bars else ""))
        )
        return cmds

    def draw_elevation(self) -> list[dict]:
        """Longitudinal flight: tread/riser profile + inclined waist + main bars + landing."""
        cmds: list[dict] = []
        total_rise = self.num_steps * self.riser
        ox = _PAD
        baseline = _PAD + total_rise  # bottom of the flight (y grows downward)

        # Step profile (going then riser, climbing right-and-up).
        x, y = ox, baseline
        for _ in range(self.num_steps):
            cmds.append(self.line(x, y, x + self.going, y, "structural_outline"))  # tread
            cmds.append(self.line(x + self.going, y, x + self.going, y - self.riser, "structural_outline"))  # riser
            x += self.going
            y -= self.riser
        flight_end_x, flight_end_y = x, y

        # Inclined waist soffit, offset below the step nosings.
        soffit = self.waist
        cmds.append(
            self.line(ox, baseline + soffit, flight_end_x, flight_end_y + soffit, "structural_outline")
        )

        # Main tension bars following the soffit.
        dia = self._main_dia()
        cmds.append(
            self.line(ox + self.cover, baseline + soffit - self.cover - dia / 2,
                      flight_end_x - self.cover, flight_end_y + soffit - self.cover - dia / 2,
                      "rebar", diameter=dia, mark=self._main_mark())
        )

        # Top landing.
        cmds.append(self.rect(flight_end_x, flight_end_y, self.landing, soffit, "structural_outline"))
        return cmds

    def draw_dimensions(self) -> list[dict]:
        return [
            self.dimension("vertical", self.waist, f"waist = {self.waist:.0f}", x=_PAD - 30, y=_PAD),
            self.dimension("vertical", self.riser, f"R = {self.riser:.0f}", x=_PAD - 15, y=_PAD),
            self.dimension("horizontal", self.going, f"G = {self.going:.0f}", x=_PAD, y=_PAD - 15),
            self.dimension("horizontal", self.span, f"span = {self.span:.0f}", x=_PAD, y=_PAD - 30),
        ]

    def draw_bar_marks(self) -> list[dict]:
        cmds: list[dict] = []
        dia = self._main_dia()
        spacing = self.main_bars[0].get("spacing", 150) if self.main_bars else 150
        cmds.append(self.text(f"T{dia:.0f}@{spacing} (main, soffit)", _PAD + 10, _PAD + self.num_steps * self.riser + 40, "bar_mark"))
        if self.distribution_bars:
            ddia = self.distribution_bars[0].get("diameter", 10)
            dsp = self.distribution_bars[0].get("spacing", 250)
            cmds.append(self.text(f"T{ddia}@{dsp} (distribution)", _PAD + 10, _PAD + self.num_steps * self.riser + 56, "bar_mark"))
        return cmds

    def draw_annotations(self) -> list[dict]:
        fcu = self.design.get("fcu_MPa", self.design.get("fck_MPa", 30))
        return [
            self.text(f"STAIRCASE {self.member_id} — FLIGHT", _PAD, _PAD - 30, "title"),
            self.text(
                f"{self.num_steps} treads @ R{self.riser:.0f}/G{self.going:.0f} | "
                f"waist {self.waist:.0f} | fcu = {fcu} MPa | cover {self.cover:.0f}",
                _PAD, _PAD - 15, "subtitle",
            ),
        ]

    def canvas_bounds(self) -> dict:
        total_rise = self.num_steps * self.riser
        width = self.num_steps * self.going + self.landing + 2 * _PAD
        height = total_rise + self.waist + 2 * _PAD + 60
        return {"width": max(width, 500), "height": max(height, 500)}

    def drawing_scale(self) -> int:
        return 50

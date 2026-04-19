"""
Module 1 — Calculation Sheet Engine
=====================================
Transforms a ``ReportMember`` into a structured data dict ready for Jinja2
template rendering. Also provides:

  * ``BMDGenerator``  — builds inline SVG for Bending Moment Diagrams.
  * ``SFDGenerator``  — builds inline SVG for Shear Force Diagrams.

This module **never calculates**. It only reads, formats, and prepares
structured data from the upstream ``ReportDataModel``.

Classes
-------
CalcSheetEngine
    Main entry point. ``build(member)`` returns a fully-populated context
    dict for the Jinja2 template renderer.
BMDGenerator
    Generates an inline SVG string for a bending moment diagram.
SFDGenerator
    Generates an inline SVG string for a shear force diagram.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from core.reporting.normalizer import ReportDataModel, ReportMember, ReportProject


# ---------------------------------------------------------------------------
# SVG Constants
# ---------------------------------------------------------------------------
SVG_WIDTH = 700          # px — total diagram viewport width
SVG_HEIGHT = 200         # px — diagram area height
SVG_MARGIN_LEFT = 60     # px — space for axis labels
SVG_MARGIN_RIGHT = 20    # px
SVG_MARGIN_TOP = 30      # px
SVG_MARGIN_BOTTOM = 40   # px
DIAGRAM_W = SVG_WIDTH - SVG_MARGIN_LEFT - SVG_MARGIN_RIGHT
DIAGRAM_H = SVG_HEIGHT - SVG_MARGIN_TOP - SVG_MARGIN_BOTTOM


# ---------------------------------------------------------------------------
# BMD Generator
# ---------------------------------------------------------------------------

class BMDGenerator:
    """
    Generates an inline SVG string representing a Bending Moment Diagram (BMD).

    The diagram reads moment values at critical sections from the
    ``analysis_output`` dict and renders them as a filled curve
    (positive / sagging below baseline, negative / hogging above).

    Colour convention
    -----------------
    * Sagging (positive)  → filled area below the baseline, colour #3B82F6 (blue).
    * Hogging  (negative) → filled area above the baseline, colour #EF4444 (red).

    Parameters
    ----------
    analysis_output : dict
        Analysis Engine output containing at minimum ``bmd_points`` — a list of
        ``{position_m, moment_kNm}`` dicts. If absent, a placeholder is rendered.
    span_m : float
        Total member span in metres. Used to scale the x-axis.

    Returns
    -------
    str
        Self-contained SVG markup (no external dependencies).
    """

    def generate(self, analysis_output: dict, span_m: float) -> str:
        """
        Build and return the BMD as an inline SVG string.

        Parameters
        ----------
        analysis_output : dict
            Must contain ``bmd_points`` list of ``{position_m, moment_kNm}``.
        span_m : float
            Total span in metres for x-axis scaling.

        Returns
        -------
        str
            Complete ``<svg>...</svg>`` markup.
        """
        points = analysis_output.get("bmd_points", [])
        if not points:
            points = self._placeholder_points(span_m)

        # Scale
        x_scale = DIAGRAM_W / max(span_m, 0.001)
        moments = [p["moment_kNm"] for p in points]
        m_max = max(abs(m) for m in moments) if moments else 1.0
        if m_max == 0:
            m_max = 1.0
        y_scale = (DIAGRAM_H / 2.0) / m_max

        # Baseline y in SVG coords (centre of diagram area)
        baseline_y = SVG_MARGIN_TOP + DIAGRAM_H / 2.0

        # Build polyline data
        curve_pts: list[tuple[float, float]] = []
        for p in points:
            x = SVG_MARGIN_LEFT + p["position_m"] * x_scale
            # Positive moment → below baseline (↓ in SVG = larger y)
            y = baseline_y - p["moment_kNm"] * y_scale
            curve_pts.append((x, y))

        svg_lines = self._build_svg(curve_pts, baseline_y, m_max, span_m, points)
        return svg_lines

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _placeholder_points(span_m: float) -> list[dict]:
        """Return a simple parabolic sagging BMD for a UDL beam."""
        n = 10
        pts = []
        for i in range(n + 1):
            xi = i * span_m / n
            # Parabola: M = w·L/2·x − w·x²/2 (normalised: unity UDL → M_max at midspan)
            m = (span_m / 2.0 * xi - xi ** 2 / 2.0) * (8.0 / span_m ** 2)  # normalised
            pts.append({"position_m": xi, "moment_kNm": m})
        return pts

    @staticmethod
    def _build_svg(
        curve_pts: list[tuple[float, float]],
        baseline_y: float,
        m_max: float,
        span_m: float,
        raw_points: list[dict],
    ) -> str:
        """Compose the complete SVG markup."""
        total_w = SVG_WIDTH
        total_h = SVG_HEIGHT

        # Polygon points for fill: close path at baseline
        first_x = curve_pts[0][0]
        last_x = curve_pts[-1][0]
        poly_pts = f"{first_x:.1f},{baseline_y:.1f} "
        poly_pts += " ".join(f"{x:.1f},{y:.1f}" for x, y in curve_pts)
        poly_pts += f" {last_x:.1f},{baseline_y:.1f}"

        # Separate above/below polygons using clip paths (sagging vs hogging)
        below_clip = f"M {first_x:.1f} {baseline_y:.1f} " + " ".join(
            f"L {x:.1f} {y:.1f}" for x, y in curve_pts
        ) + f" L {last_x:.1f} {baseline_y:.1f} Z"

        # Peak labels
        labels: list[str] = []
        # Find peak sagging and hogging
        max_sag = max((p for p in raw_points if p["moment_kNm"] >= 0), key=lambda p: p["moment_kNm"], default=None)
        max_hog = min((p for p in raw_points if p["moment_kNm"] < 0), key=lambda p: p["moment_kNm"], default=None)

        if max_sag:
            x_scale = DIAGRAM_W / max(span_m, 0.001)
            y_scale = (DIAGRAM_H / 2.0) / m_max
            lx = SVG_MARGIN_LEFT + max_sag["position_m"] * x_scale
            ly = baseline_y - max_sag["moment_kNm"] * y_scale - 6
            labels.append(
                f'<text x="{lx:.1f}" y="{ly:.1f}" '
                f'font-size="10" fill="#1E40AF" text-anchor="middle">'
                f'+{max_sag["moment_kNm"]:.1f} kNm</text>'
            )
        if max_hog:
            x_scale = DIAGRAM_W / max(span_m, 0.001)
            y_scale = (DIAGRAM_H / 2.0) / m_max
            lx = SVG_MARGIN_LEFT + max_hog["position_m"] * x_scale
            ly = baseline_y - max_hog["moment_kNm"] * y_scale + 14
            labels.append(
                f'<text x="{lx:.1f}" y="{ly:.1f}" '
                f'font-size="10" fill="#B91C1C" text-anchor="middle">'
                f'{max_hog["moment_kNm"]:.1f} kNm</text>'
            )

        right_x = SVG_MARGIN_LEFT + DIAGRAM_W

        return f"""<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 {total_w} {total_h}"
     width="{total_w}" height="{total_h}"
     role="img" aria-label="Bending Moment Diagram">
  <defs>
    <clipPath id="bmd-below">
      <rect x="{SVG_MARGIN_LEFT}" y="{baseline_y:.1f}"
            width="{DIAGRAM_W}" height="{DIAGRAM_H / 2:.1f}"/>
    </clipPath>
    <clipPath id="bmd-above">
      <rect x="{SVG_MARGIN_LEFT}" y="{SVG_MARGIN_TOP}"
            width="{DIAGRAM_W}" height="{DIAGRAM_H / 2:.1f}"/>
    </clipPath>
  </defs>
  <!-- Axes -->
  <line x1="{SVG_MARGIN_LEFT}" y1="{SVG_MARGIN_TOP}"
        x2="{SVG_MARGIN_LEFT}" y2="{SVG_MARGIN_TOP + DIAGRAM_H}"
        stroke="#94A3B8" stroke-width="1"/>
  <line x1="{SVG_MARGIN_LEFT}" y1="{baseline_y:.1f}"
        x2="{right_x}" y2="{baseline_y:.1f}"
        stroke="#1E293B" stroke-width="1.5"/>
  <!-- Sagging fill (below baseline, blue) -->
  <polygon points="{poly_pts}" fill="#BFDBFE" stroke="none" clip-path="url(#bmd-below)"/>
  <!-- Hogging fill (above baseline, red) -->
  <polygon points="{poly_pts}" fill="#FECACA" stroke="none" clip-path="url(#bmd-above)"/>
  <!-- Curve -->
  <polyline points="{' '.join(f'{x:.1f},{y:.1f}' for x, y in curve_pts)}"
            fill="none" stroke="#1E40AF" stroke-width="2"/>
  <!-- Labels -->
  {''.join(labels)}
  <!-- Axis labels -->
  <text x="{SVG_MARGIN_LEFT - 5}" y="{SVG_MARGIN_TOP - 5}"
        font-size="9" fill="#64748B" text-anchor="end">M (kNm)</text>
  <text x="{right_x}" y="{SVG_MARGIN_TOP + DIAGRAM_H + 18}"
        font-size="9" fill="#64748B" text-anchor="end">x (m)</text>
  <text x="{SVG_MARGIN_LEFT + DIAGRAM_W / 2}" y="{SVG_MARGIN_TOP + DIAGRAM_H + 30}"
        font-size="9" fill="#64748B" text-anchor="middle">Bending Moment Diagram</text>
  <!-- Span label -->
  <text x="{SVG_MARGIN_LEFT}" y="{SVG_MARGIN_TOP + DIAGRAM_H + 18}"
        font-size="9" fill="#64748B">0</text>
  <text x="{right_x}" y="{SVG_MARGIN_TOP + DIAGRAM_H + 18}"
        font-size="9" fill="#64748B" text-anchor="end">{span_m:.1f}</text>
</svg>"""


# ---------------------------------------------------------------------------
# SFD Generator
# ---------------------------------------------------------------------------

class SFDGenerator:
    """
    Generates an inline SVG string representing a Shear Force Diagram (SFD).

    Shear force diagrams are step functions between supports. The diagram
    reads ``sfd_points`` from the analysis output and renders a stepped
    profile.

    Colour convention
    -----------------
    * Positive shear → filled area below baseline, colour #10B981 (green).
    * Negative shear → filled area above baseline, colour #F59E0B (amber).

    Parameters
    ----------
    analysis_output : dict
        Analysis Engine output containing ``sfd_points`` — list of
        ``{position_m, shear_kN}`` dicts.
    span_m : float
        Total member span in metres.
    """

    def generate(self, analysis_output: dict, span_m: float) -> str:
        """
        Build and return the SFD as an inline SVG string.

        Parameters
        ----------
        analysis_output : dict
            Must contain ``sfd_points`` list of ``{position_m, shear_kN}``.
        span_m : float
            Total span in metres.

        Returns
        -------
        str
            Complete ``<svg>...</svg>`` markup.
        """
        points = analysis_output.get("sfd_points", [])
        if not points:
            points = self._placeholder_points(span_m)

        x_scale = DIAGRAM_W / max(span_m, 0.001)
        shears = [p["shear_kN"] for p in points]
        v_max = max(abs(v) for v in shears) if shears else 1.0
        if v_max == 0:
            v_max = 1.0
        y_scale = (DIAGRAM_H / 2.0) / v_max
        baseline_y = SVG_MARGIN_TOP + DIAGRAM_H / 2.0

        # Build step-function polyline
        step_pts: list[tuple[float, float]] = []
        for i, p in enumerate(points):
            x = SVG_MARGIN_LEFT + p["position_m"] * x_scale
            y = baseline_y - p["shear_kN"] * y_scale
            if i > 0:
                # Horizontal step first (stay at previous x, jump to new y)
                step_pts.append((x, step_pts[-1][1]))
            step_pts.append((x, y))

        return self._build_svg(step_pts, baseline_y, v_max, span_m, points)

    @staticmethod
    def _placeholder_points(span_m: float) -> list[dict]:
        """Return a typical simply-supported beam SFD (UDL)."""
        w = 1.0
        L = span_m
        return [
            {"position_m": 0.0,      "shear_kN": w * L / 2},
            {"position_m": L / 2.0,  "shear_kN": 0.0},
            {"position_m": L,        "shear_kN": -w * L / 2},
        ]

    @staticmethod
    def _build_svg(
        step_pts: list[tuple[float, float]],
        baseline_y: float,
        v_max: float,
        span_m: float,
        raw_points: list[dict],
    ) -> str:
        """Compose SFD SVG markup."""
        total_w = SVG_WIDTH
        total_h = SVG_HEIGHT
        first_x = step_pts[0][0]
        last_x = step_pts[-1][0]
        right_x = SVG_MARGIN_LEFT + DIAGRAM_W

        # Build polygon
        poly_pts = f"{first_x:.1f},{baseline_y:.1f} "
        poly_pts += " ".join(f"{x:.1f},{y:.1f}" for x, y in step_pts)
        poly_pts += f" {last_x:.1f},{baseline_y:.1f}"

        # Peak labels
        labels: list[str] = []
        if raw_points:
            x_scale = DIAGRAM_W / max(span_m, 0.001)
            y_scale = (DIAGRAM_H / 2.0) / v_max
            max_v = max(raw_points, key=lambda p: abs(p["shear_kN"]))
            lx = SVG_MARGIN_LEFT + max_v["position_m"] * x_scale
            ly = baseline_y - max_v["shear_kN"] * y_scale - 8
            labels.append(
                f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="10" '
                f'fill="#065F46" text-anchor="middle">'
                f'{max_v["shear_kN"]:.1f} kN</text>'
            )

        pts_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in step_pts)

        return f"""<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 {total_w} {total_h}"
     width="{total_w}" height="{total_h}"
     role="img" aria-label="Shear Force Diagram">
  <defs>
    <clipPath id="sfd-below">
      <rect x="{SVG_MARGIN_LEFT}" y="{baseline_y:.1f}"
            width="{DIAGRAM_W}" height="{DIAGRAM_H / 2:.1f}"/>
    </clipPath>
    <clipPath id="sfd-above">
      <rect x="{SVG_MARGIN_LEFT}" y="{SVG_MARGIN_TOP}"
            width="{DIAGRAM_W}" height="{DIAGRAM_H / 2:.1f}"/>
    </clipPath>
  </defs>
  <line x1="{SVG_MARGIN_LEFT}" y1="{SVG_MARGIN_TOP}"
        x2="{SVG_MARGIN_LEFT}" y2="{SVG_MARGIN_TOP + DIAGRAM_H}"
        stroke="#94A3B8" stroke-width="1"/>
  <line x1="{SVG_MARGIN_LEFT}" y1="{baseline_y:.1f}"
        x2="{right_x}" y2="{baseline_y:.1f}"
        stroke="#1E293B" stroke-width="1.5"/>
  <polygon points="{poly_pts}" fill="#A7F3D0" stroke="none" clip-path="url(#sfd-below)"/>
  <polygon points="{poly_pts}" fill="#FDE68A" stroke="none" clip-path="url(#sfd-above)"/>
  <polyline points="{pts_str}" fill="none" stroke="#059669" stroke-width="2"/>
  {''.join(labels)}
  <text x="{SVG_MARGIN_LEFT - 5}" y="{SVG_MARGIN_TOP - 5}"
        font-size="9" fill="#64748B" text-anchor="end">V (kN)</text>
  <text x="{SVG_MARGIN_LEFT + DIAGRAM_W / 2}" y="{SVG_MARGIN_TOP + DIAGRAM_H + 30}"
        font-size="9" fill="#64748B" text-anchor="middle">Shear Force Diagram</text>
  <text x="{SVG_MARGIN_LEFT}" y="{SVG_MARGIN_TOP + DIAGRAM_H + 18}"
        font-size="9" fill="#64748B">0</text>
  <text x="{right_x}" y="{SVG_MARGIN_TOP + DIAGRAM_H + 18}"
        font-size="9" fill="#64748B" text-anchor="end">{span_m:.1f} m</text>
</svg>"""


# ---------------------------------------------------------------------------
# Calculation Sheet Engine
# ---------------------------------------------------------------------------

class CalcSheetEngine:
    """
    Module 1: Calculation Sheet Engine.

    Builds the full template context dict for one member's calculation sheet.
    The context is consumed by ``renderer.TemplateRenderer`` and the
    appropriate Jinja2 template in ``templates/members/``.

    This class never computes values. All numbers are sourced from the
    ``ReportMember`` object.

    Parameters
    ----------
    None — stateless class, instantiate once and reuse.

    Usage
    -----
    ::

        engine = CalcSheetEngine()
        ctx = engine.build(project, member)
        # Pass ctx to TemplateRenderer.render_member(member_type, ctx)
    """

    _bmd = BMDGenerator()
    _sfd = SFDGenerator()

    def build(self, project: ReportProject, member: ReportMember) -> dict[str, Any]:
        """
        Build the full Jinja2 template context for one member's calculation sheet.

        Parameters
        ----------
        project : ReportProject
            Project-level metadata (header fields).
        member : ReportMember
            Normalised member data from the Report Data Model.

        Returns
        -------
        dict
            Complete context dict with all keys required by the member
            Jinja2 template. Structure:

            * ``project``      — ReportProject (forwarded as-is)
            * ``member``       — ReportMember (forwarded as-is)
            * ``design_basis`` — Material properties and partial factors
            * ``loading``      — Load sources and design load table
            * ``analysis``     — Critical section values table + SVG diagrams
            * ``calc_steps``   — List of structured calculation trace steps
            * ``results``      — Final member sizes, reinforcement, pass/fail
            * ``bmd_svg``      — Inline SVG string for BMD (or empty string)
            * ``sfd_svg``      — Inline SVG string for SFD (or empty string)
        """
        ao = member.analysis_output
        lo = member.loading_output
        do = member.design_output

        # Span for diagram scaling
        span_m = self._get_span_m(member)

        # BMD / SFD SVGs
        bmd_svg = self._bmd.generate(ao, span_m)
        sfd_svg = self._sfd.generate(ao, span_m)

        return {
            "project": project,
            "member": member,
            "design_basis": self._build_design_basis(member, do),
            "loading": self._build_loading(lo),
            "analysis": self._build_analysis(ao),
            "calc_steps": member.calculation_trace,
            "results": self._build_results(member, do),
            "bmd_svg": bmd_svg,
            "sfd_svg": sfd_svg,
        }

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _get_span_m(member: ReportMember) -> float:
        """Extract span in metres from geometry or analysis output."""
        geom = member.geometry
        ao = member.analysis_output
        for key in ("span_m", "lx_m", "length_m"):
            if key in geom:
                return float(geom[key])
            if key in ao:
                return float(ao[key])
        # fallback: look for span in mm
        for key in ("span_mm", "lx_mm", "length_mm"):
            if key in geom:
                return float(geom[key]) / 1000.0
        return 6.0  # default sensible span

    @staticmethod
    def _build_design_basis(member: ReportMember, do: dict) -> dict:
        """Assemble the design basis section from section/material properties."""
        geom = member.geometry
        ao = member.analysis_output
        lo = member.loading_output
        return {
            "design_code": member.design_code,
            "fcu_Nmm2": geom.get("fcu", do.get("fcu", ao.get("fcu", "—"))),
            "fy_Nmm2": geom.get("fy", do.get("fy", "—")),
            "fyv_Nmm2": geom.get("fyv", do.get("fyv", "—")),
            "cover_mm": geom.get("cover", "—"),
            "gamma_c": 1.50,   # BS 8110 / EC2 concrete partial factor
            "gamma_s": 1.15,   # BS 8110 / EC2 steel partial factor
            "section_type": geom.get("section_type", member.member_type),
            "dimensions": _format_dimensions(geom),
        }

    @staticmethod
    def _build_loading(lo: dict) -> dict:
        """Format loading section from loading_output."""
        return {
            "dead_load_kNm2": lo.get("gk", lo.get("dead", "—")),
            "live_load_kNm2": lo.get("qk", lo.get("live", "—")),
            "self_weight_kNm2": lo.get("self_weight", "—"),
            "design_load_kNm2": lo.get("n_design", lo.get("design_load", "—")),
            "load_combination": lo.get("load_combination", "1.4Gk + 1.6Qk  (BS 8110 Cl 2.4.3)"),
            "partial_factors": lo.get("partial_factors", {"gamma_G": 1.4, "gamma_Q": 1.6}),
        }

    @staticmethod
    def _build_analysis(ao: dict) -> dict:
        """Format analysis results section from analysis_output."""
        return {
            "M_max_kNm": ao.get("M_max_kNm", ao.get("M_Ed_kNm", "—")),
            "V_max_kN": ao.get("V_max_kN", ao.get("V_Ed_kN", "—")),
            "N_kN": ao.get("N_kN", "—"),
            "reactions": ao.get("reactions", {}),
            "critical_sections": ao.get("critical_sections", []),
            "bmd_points": ao.get("bmd_points", []),
            "sfd_points": ao.get("sfd_points", []),
        }

    @staticmethod
    def _build_results(member: ReportMember, do: dict) -> dict:
        """Assemble the results summary section."""
        return {
            "status": member.status,
            "failed_checks": member.failed_checks,
            "near_limit_checks": member.near_limit_checks,
            "reinforcement": member.reinforcement,
            "As_req": do.get("As_req", "—"),
            "As_prov": do.get("As_prov", "—"),
            "reinforcement_description": do.get("reinforcement_description", "—"),
            "shear_links": do.get("shear_links", "—"),
            "deflection_check": do.get("deflection_check", "—"),
            "slenderness": do.get("slenderness", "—"),
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _format_dimensions(geom: dict) -> str:
    """Return a short human-readable dimension string from a geometry dict."""
    if "b" in geom and "h" in geom:
        return f"{geom['b']} × {geom['h']} mm"
    if "lx" in geom and "ly" in geom:
        return f"{geom['lx']} × {geom['ly']} mm"
    if "h" in geom:
        return f"h = {geom['h']} mm"
    return "—"

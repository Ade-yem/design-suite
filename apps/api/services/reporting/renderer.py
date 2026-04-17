"""
HTML Template Renderer
========================
Renders Jinja2 templates into HTML strings for preview and PDF export.

All templates reside in ``services/reporting/templates/``. The renderer
resolves the correct member-specific template from ``templates/members/``
and injects the full context dict produced by ``CalcSheetEngine``.

Classes
-------
TemplateRenderer
    Wraps a Jinja2 ``Environment`` and exposes ``render_member``,
    ``render_schedule``, ``render_quantities``, ``render_compliance``,
    and ``render_summary`` methods.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import jinja2


# ---------------------------------------------------------------------------
# Template path resolution
# ---------------------------------------------------------------------------

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _make_env() -> jinja2.Environment:
    """
    Create the Jinja2 environment with the reporting templates directory.

    Returns
    -------
    jinja2.Environment
        Auto-escape disabled (HTML is built by us, not user input).
        Strict undefined — missing variables raise errors immediately.
    """
    loader = jinja2.FileSystemLoader(str(_TEMPLATE_DIR))
    return jinja2.Environment(
        loader=loader,
        autoescape=False,
        undefined=jinja2.StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


# ---------------------------------------------------------------------------
# Member-type → template filename mapping
# ---------------------------------------------------------------------------

_MEMBER_TEMPLATES: dict[str, str] = {
    "beam":           "members/beam.html",
    "column":         "members/column.html",
    "slab_one_way":   "members/slab_one_way.html",
    "slab_two_way":   "members/slab_two_way.html",
    "slab_ribbed":    "members/slab_ribbed.html",
    "slab_waffle":    "members/slab_waffle.html",
    "slab_flat":      "members/slab_flat.html",
    "wall":           "members/wall.html",
    "footing_pad":    "members/footing_pad.html",
    "footing_pile":   "members/footing_pile.html",
    "staircase":      "members/staircase.html",
}

_DEFAULT_MEMBER_TEMPLATE = "members/generic.html"


class TemplateRenderer:
    """
    Renders Jinja2 templates into HTML strings.

    Instantiate once and reuse — the ``jinja2.Environment`` is cached on the
    instance.

    Parameters
    ----------
    None

    Usage
    -----
    ::

        renderer = TemplateRenderer()
        html = renderer.render_member("beam", ctx)
        html = renderer.render_compliance(compliance_ctx)
    """

    def __init__(self) -> None:
        self._env = _make_env()

    def render_member(
        self, member_type: str, context: dict[str, Any]
    ) -> str:
        """
        Render a member calculation sheet to HTML.

        Parameters
        ----------
        member_type : str
            The structural member type key (e.g. "beam", "column").
            Must match a key in ``_MEMBER_TEMPLATES`` or falls back to the
            generic template.
        context : dict
            Template context dict as produced by ``CalcSheetEngine.build()``.

        Returns
        -------
        str
            Rendered HTML string for this member's calculation sheet.
        """
        template_name = _MEMBER_TEMPLATES.get(member_type, _DEFAULT_MEMBER_TEMPLATE)
        return self._render(template_name, context)

    def render_schedule(self, context: dict[str, Any]) -> str:
        """
        Render the reinforcement schedule to HTML.

        Parameters
        ----------
        context : dict
            Template context as produced by ``RebarScheduleEngine.build()``,
            augmented with ``project`` and ``report_type`` keys.

        Returns
        -------
        str
            Rendered HTML string.
        """
        return self._render("schedule.html", context)

    def render_quantities(self, context: dict[str, Any]) -> str:
        """
        Render the material quantities report to HTML.

        Parameters
        ----------
        context : dict
            Template context as produced by ``MaterialQuantityEngine.build()``,
            augmented with ``project`` key.

        Returns
        -------
        str
            Rendered HTML string.
        """
        return self._render("quantities.html", context)

    def render_compliance(self, context: dict[str, Any]) -> str:
        """
        Render the compliance report to HTML.

        Parameters
        ----------
        context : dict
            Template context as produced by ``ComplianceReportEngine.build()``.

        Returns
        -------
        str
            Rendered HTML string.
        """
        return self._render("compliance.html", context)

    def render_summary(self, context: dict[str, Any]) -> str:
        """
        Render the project summary to HTML.

        Parameters
        ----------
        context : dict
            Template context as produced by ``ProjectSummaryEngine.build()``.

        Returns
        -------
        str
            Rendered HTML string.
        """
        return self._render("summary.html", context)

    def render_full_report(self, context: dict[str, Any]) -> str:
        """
        Render the combined full report HTML (all sheets concatenated).

        Parameters
        ----------
        context : dict
            Must contain all page HTML strings keyed as:
            - ``summary_html``
            - ``member_html_list`` — list[str], one per member
            - ``schedule_html``
            - ``quantities_html``
            - ``compliance_html``

        Returns
        -------
        str
            Full combined HTML document.
        """
        return self._render("full_report.html", context)

    # ------------------------------------------------------------------ private

    def _render(self, template_name: str, context: dict[str, Any]) -> str:
        """Load and render a template by name."""
        try:
            template = self._env.get_template(template_name)
        except jinja2.TemplateNotFound:
            raise FileNotFoundError(
                f"Reporting template not found: '{template_name}'. "
                f"Expected at: {_TEMPLATE_DIR / template_name}"
            )
        except jinja2.UndefinedError as exc:
            raise ValueError(
                f"Template '{template_name}' references an undefined variable: {exc}"
            )
        return template.render(**context)

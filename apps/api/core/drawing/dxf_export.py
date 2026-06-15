"""
core/drawing/dxf_export.py
==========================
DXF export engine — converts the drawing-primitive command sets produced by the
drafter (``core.drawing.generate_drawing_commands``) into a DXF file.

This mirrors ``core.reporting.pdf_export.PDFExportEngine``: a thin, lazily
imported wrapper around an optional third-party library (``ezdxf``) that turns
in-memory drawing data into downloadable bytes.

Input shape
-----------
Each drawing dict looks like::

    {
      "member_id": "B1",
      "member_type": "beam",
      "commands": {
        "section":     [<primitive>, ...],
        "elevation":   [<primitive>, ...],
        "dimensions":  [<primitive>, ...],
        "bar_marks":   [<primitive>, ...],
        "annotations": [<primitive>, ...],
        "canvas_bounds": {"width": float, "height": float},
        "scale": int,
      },
    }

A *primitive* is one of the dicts emitted by ``BaseDrawingGenerator``:
``rect``, ``circle``, ``line``, ``text`` or ``dimension`` (all coordinates in
mm, screen convention with y pointing **down**).

Coordinate convention
----------------------
DXF model space is y-**up**, so every y is negated on import. Each member is
laid out in its own row; within a member the *section* view and the
*elevation* group (elevation + dimensions + bar marks + annotations) are placed
in two columns so they do not overlap.
"""
from __future__ import annotations

import io
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Layer name per command group, with an AutoCAD Color Index (ACI).
_GROUP_LAYERS: dict[str, tuple[str, int]] = {
    "section":     ("STRUCT-SECTION", 7),     # white/black
    "elevation":   ("STRUCT-ELEVATION", 7),
    "dimensions":  ("STRUCT-DIMENSIONS", 3),   # green
    "bar_marks":   ("STRUCT-BARMARKS", 1),     # red
    "annotations": ("STRUCT-ANNOTATIONS", 5),  # blue
    "_labels":     ("STRUCT-LABELS", 2),       # yellow
}

_COLUMN_GAP = 1500.0   # mm horizontal gap between section and elevation blocks
_ROW_GAP = 2000.0      # mm vertical gap between members
_TEXT_HEIGHT = 120.0   # mm default text height for labels


class DXFExportEngine:
    """Convert drawing command sets to DXF bytes via ``ezdxf``."""

    def export(self, drawings: list[dict[str, Any]], *, title: Optional[str] = None) -> bytes:
        """
        Render one or more member drawings into a single DXF document.

        Parameters
        ----------
        drawings : list[dict]
            Drawing dicts (see module docstring). May contain a single member
            (per-member export) or many (whole-project export).
        title : str, optional
            Project reference used in the DXF as a header comment.

        Returns
        -------
        bytes
            The DXF document encoded as UTF-8 (ASCII DXF is a text format).

        Raises
        ------
        ImportError
            If ``ezdxf`` is not installed.
        RuntimeError
            If document construction fails.
        """
        try:
            import ezdxf
        except ImportError as exc:  # pragma: no cover - exercised only without ezdxf
            raise ImportError(
                "ezdxf is required for DXF export. Install it with `pip install ezdxf`."
            ) from exc

        try:
            doc = ezdxf.new("R2010")
            if title:
                doc.header["$PROJECTNAME"] = str(title)[:255]
            msp = doc.modelspace()

            for name, (layer, color) in _GROUP_LAYERS.items():
                if layer not in doc.layers:
                    doc.layers.add(layer, color=color)

            row_top = 0.0
            for drawing in drawings:
                row_top = self._place_member(msp, drawing, row_top)

            stream = io.StringIO()
            doc.write(stream)
            return stream.getvalue().encode("utf-8")
        except ImportError:
            raise
        except Exception as exc:
            raise RuntimeError(f"DXF export failed: {exc}") from exc

    # ── Internal layout ──────────────────────────────────────────────────────

    def _place_member(self, msp, drawing: dict[str, Any], row_top: float) -> float:
        """Place one member's views below ``row_top``; return the next row top."""
        commands = drawing.get("commands", {}) or {}
        member_id = str(drawing.get("member_id", "member"))

        section = self._collect(commands.get("section", []), "section")
        elevation = []
        for group in ("elevation", "dimensions", "bar_marks", "annotations"):
            elevation.extend(self._collect(commands.get(group, []), group))

        sec_bounds = _bounds(section)
        elev_bounds = _bounds(elevation)

        # Member label sits a little above the row.
        label_y = row_top + _TEXT_HEIGHT * 2.0
        self._emit_text(msp, f"{member_id} ({drawing.get('member_type', '')})",
                        0.0, label_y, _GROUP_LAYERS["_labels"][0], _TEXT_HEIGHT * 1.5)

        # Section column anchored at x=0; elevation column to its right.
        sec_dx = -sec_bounds[0]
        sec_dy = row_top - sec_bounds[3]            # top of view aligns to row_top
        self._emit(msp, section, sec_dx, sec_dy)

        sec_width = (sec_bounds[2] - sec_bounds[0]) if section else 0.0
        elev_dx = (sec_width + _COLUMN_GAP) - elev_bounds[0]
        elev_dy = row_top - elev_bounds[3]
        self._emit(msp, elevation, elev_dx, elev_dy)

        sec_height = (sec_bounds[3] - sec_bounds[1]) if section else 0.0
        elev_height = (elev_bounds[3] - elev_bounds[1]) if elevation else 0.0
        row_height = max(sec_height, elev_height, _TEXT_HEIGHT * 3.0)
        return row_top - row_height - _ROW_GAP

    # ── Primitive parsing (screen → y-up shapes) ─────────────────────────────

    def _collect(self, primitives: list[dict[str, Any]], group: str) -> list[dict[str, Any]]:
        """Convert raw screen-space primitives into y-up internal shapes."""
        layer = _GROUP_LAYERS.get(group, _GROUP_LAYERS["annotations"])[0]
        shapes: list[dict[str, Any]] = []
        for p in primitives or []:
            kind = p.get("type")
            if kind == "rect":
                x, y, w, h = p.get("x", 0.0), p.get("y", 0.0), p.get("width", 0.0), p.get("height", 0.0)
                pts = [(x, -y), (x + w, -y), (x + w, -y - h), (x, -y - h)]
                shapes.append({"k": "poly", "pts": pts, "layer": layer})
            elif kind == "circle":
                shapes.append({"k": "circle", "c": (p.get("cx", 0.0), -p.get("cy", 0.0)),
                               "r": p.get("r", 0.0), "layer": layer})
            elif kind == "line":
                shapes.append({"k": "line",
                               "a": (p.get("x1", 0.0), -p.get("y1", 0.0)),
                               "b": (p.get("x2", 0.0), -p.get("y2", 0.0)), "layer": layer})
            elif kind == "text":
                shapes.append({"k": "text", "t": str(p.get("text", "")),
                               "p": (p.get("x", 0.0), -p.get("y", 0.0)), "layer": layer})
            elif kind == "dimension":
                # Render the dimension label as text; full DXF DIMENSION entities
                # are intentionally avoided for portability.
                shapes.append({"k": "text", "t": str(p.get("label", "")),
                               "p": (p.get("x", 0.0), -p.get("y", 0.0)), "layer": layer})
        return shapes

    # ── Emission with translation ────────────────────────────────────────────

    def _emit(self, msp, shapes: list[dict[str, Any]], dx: float, dy: float) -> None:
        for s in shapes:
            k = s["k"]
            attrs = {"layer": s["layer"]}
            if k == "poly":
                pts = [(x + dx, y + dy) for x, y in s["pts"]]
                msp.add_lwpolyline(pts, close=True, dxfattribs=attrs)
            elif k == "line":
                msp.add_line((s["a"][0] + dx, s["a"][1] + dy),
                             (s["b"][0] + dx, s["b"][1] + dy), dxfattribs=attrs)
            elif k == "circle":
                if s["r"] > 0:
                    msp.add_circle((s["c"][0] + dx, s["c"][1] + dy), s["r"], dxfattribs=attrs)
            elif k == "text" and s["t"]:
                self._emit_text(msp, s["t"], s["p"][0] + dx, s["p"][1] + dy, s["layer"], _TEXT_HEIGHT)

    @staticmethod
    def _emit_text(msp, content: str, x: float, y: float, layer: str, height: float) -> None:
        entity = msp.add_text(content, height=height, dxfattribs={"layer": layer})
        # ezdxf >= 0.17 uses set_placement; guard for older variants.
        try:
            entity.set_placement((x, y))
        except AttributeError:  # pragma: no cover
            entity.dxf.insert = (x, y)


def _bounds(shapes: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    """Return (min_x, min_y, max_x, max_y) over a list of internal shapes."""
    xs: list[float] = []
    ys: list[float] = []
    for s in shapes:
        if s["k"] == "poly":
            xs.extend(x for x, _ in s["pts"])
            ys.extend(y for _, y in s["pts"])
        elif s["k"] == "line":
            xs.extend((s["a"][0], s["b"][0]))
            ys.extend((s["a"][1], s["b"][1]))
        elif s["k"] == "circle":
            xs.extend((s["c"][0] - s["r"], s["c"][0] + s["r"]))
            ys.extend((s["c"][1] - s["r"], s["c"][1] + s["r"]))
        elif s["k"] == "text":
            xs.append(s["p"][0])
            ys.append(s["p"][1])
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


dxf_export_engine = DXFExportEngine()

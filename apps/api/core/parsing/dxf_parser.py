"""
dxf_geometric_extractor.py
===========================
Stage 1 of the Structural Design Copilot parser pipeline.

Responsibility:
    Faithfully transcribe all geometric entities from a DXF file into a
    normalized, unit-consistent Raw Geometry JSON. This module performs
    NO structural interpretation — it is purely deterministic geometry
    extraction. All coordinates are normalized to millimetres.

Handles the full range of real-world structural engineer drawing practices:
    - Lines and polylines used as member centre-lines or outlines
    - Closed polylines / hatched regions used as section outlines
    - INSERT blocks for column grids, section symbols, title blocks
    - CIRCLE entities for circular columns or holes
    - ARC entities for curved members or detail callouts
    - TEXT / MTEXT for member labels, grid references, dimension annotations
    - DIMENSION entities for annotated dimensions
    - Inconsistent / non-standard layer naming conventions
    - Mixed unit files (drawing units vs annotation units)
    - Multiple model-space layouts (some firms split floors across layouts)

Author:  Structural Design Copilot — Parser Module
"""

from __future__ import annotations

import logging
import math
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf import units
from ezdxf.document import Drawing
from ezdxf.entities import (
    Arc,
    Circle,
    DXFGraphic,
    Insert,
    LWPolyline,
    Line,
    MText,
    Polyline,
    Spline,
    Text,
)
from ezdxf.layouts import Layout
from ezdxf.math import BoundingBox2d, Matrix44, Vec2, Vec3

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)


# ---------------------------------------------------------------------------
# Constants — unit conversion to millimetres
# ---------------------------------------------------------------------------
# ezdxf exposes $INSUNITS as an integer enum value.
# Reference: https://ezdxf.readthedocs.io/en/stable/concepts/units.html
INSUNITS_TO_MM: dict[int, float] = {
    0:  1.0,       # Unitless — treat as mm, warn user
    1:  25.4,      # Inches
    2:  304.8,     # Feet
    3:  1609344.0, # Miles
    4:  1.0,       # Millimetres (native)
    5:  10.0,      # Centimetres
    6:  1000.0,    # Metres
    7:  1_000_000.0,  # Kilometres
    8:  0.0000254, # Microinches
    9:  0.0254,    # Mils
    10: 914.4,     # Yards
    13: 1.0,       # Unitless (alternate)
    14: 1e-7,      # Angstroms
    15: 1e-4,      # Nanometres
    16: 0.001,     # Microns
    17: 100.0,     # Decimetres
    18: 10000.0,   # Decametres
    19: 100000.0,  # Hectometres
    20: 1e9,       # Gigametres
    21: 1.496e14,  # Astronomical units
    22: 9.461e18,  # Light years
    23: 3.086e19,  # Parsecs
}

# Spatial grid cell size in mm for proximity grouping
SPATIAL_HASH_CELL_MM = 500.0

# Minimum line length to be considered a structural member (not a hatch line)
MIN_MEMBER_LENGTH_MM = 100.0

# Aspect ratio threshold — bounding boxes below this are considered "square"
# (i.e., column-like) vs elongated (beam-like)
SQUARE_ASPECT_THRESHOLD = 1.5


# ---------------------------------------------------------------------------
# Layer classification heuristics
# ---------------------------------------------------------------------------
# These are HINTS only — the AI agent makes the final call.
# Patterns are tested case-insensitively against the full layer name.
# Order matters: first match wins.

LAYER_HINT_PATTERNS: list[tuple[str, str]] = [
    # --- Structural annotations / text / dimensions (First match wins, so check text first to avoid BeamText matching beam) ---
    (r"text",               "dimension_annotation"),
    (r"txt",                "dimension_annotation"),
    (r"label",              "dimension_annotation"),
    (r"note",               "dimension_annotation"),
    (r"dim",                "dimension_annotation"),
    (r"annotation",         "dimension_annotation"),
    (r"s[_\-]?note",        "dimension_annotation"),
    (r"s[_\-]?text",        "dimension_annotation"),

    # --- Structural members ---
    (r"s[_\-]?col",         "column_candidate"),
    (r"str[_\-]?col",       "column_candidate"),
    (r"column",             "column_candidate"),
    (r"pillar",             "column_candidate"),
    (r"pile",               "pile_candidate"),

    (r"s[_\-]?beam",        "beam_candidate"),
    (r"str[_\-]?beam",      "beam_candidate"),
    (r"beam",               "beam_candidate"),
    (r"s[_\-]?bm",          "beam_candidate"),
    (r"lintel",             "beam_candidate"),

    (r"s[_\-]?slab",        "slab_candidate"),
    (r"str[_\-]?slab",      "slab_candidate"),
    (r"slab",               "slab_candidate"),
    (r"floor",              "slab_candidate"),
    (r"soffit",             "slab_candidate"),

    (r"s[_\-]?wall",        "wall_candidate"),
    (r"str[_\-]?wall",      "wall_candidate"),
    (r"shear[_\-]?wall",    "wall_candidate"),
    (r"retaining",          "wall_candidate"),

    (r"s[_\-]?fdn",         "foundation_candidate"),
    (r"foundation",         "foundation_candidate"),
    (r"footing",            "foundation_candidate"),
    (r"pad",                "foundation_candidate"),
    (r"raft",               "foundation_candidate"),
    (r"pile[_\-]?cap",      "foundation_candidate"),

    (r"s[_\-]?stair",       "stair_candidate"),
    (r"stair",              "stair_candidate"),

    (r"rebar",              "reinforcement_annotation"),
    (r"reinf",              "reinforcement_annotation"),
    (r"bar",                "reinforcement_annotation"),

    # --- Structural annotations / grids ---
    (r"grid",               "grid_line"),
    (r"s[_\-]?grid",        "grid_line"),
    (r"column[_\-]?grid",   "grid_line"),
    (r"ref[_\-]?line",      "grid_line"),

    # --- Architectural (to be deprioritised, not deleted) ---
    (r"^a[_\-]",            "architectural"),
    (r"arch",               "architectural"),
    (r"a[_\-]?wall",        "architectural"),
    (r"a[_\-]?door",        "architectural"),
    (r"a[_\-]?window",      "architectural"),
    (r"a[_\-]?furn",        "architectural"),
    (r"furniture",          "architectural"),
    (r"hatch",              "architectural"),

    # --- MEP / Services (ignore) ---
    (r"^m[_\-]",            "mep_ignore"),
    (r"^e[_\-]",            "mep_ignore"),
    (r"^p[_\-]",            "mep_ignore"),
    (r"mechanical",         "mep_ignore"),
    (r"electrical",         "mep_ignore"),
    (r"plumbing",           "mep_ignore"),
    (r"hvac",               "mep_ignore"),

    # --- Title blocks / borders ---
    (r"title",              "title_block"),
    (r"border",             "title_block"),
    (r"frame",              "title_block"),
    (r"defpoints",          "title_block"),
]

_COMPILED_LAYER_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(pat, re.IGNORECASE), hint)
    for pat, hint in LAYER_HINT_PATTERNS
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BoundingBox:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @property
    def centroid(self) -> tuple[float, float]:
        return (
            (self.min_x + self.max_x) / 2.0,
            (self.min_y + self.max_y) / 2.0,
        )

    @property
    def aspect_ratio(self) -> float:
        """height / width. >SQUARE_ASPECT_THRESHOLD → elongated (beam-like)."""
        if self.width < 1e-6:
            return float("inf")
        return self.height / self.width

    def to_dict(self) -> dict:
        return {
            "min": [round(self.min_x, 4), round(self.min_y, 4)],
            "max": [round(self.max_x, 4), round(self.max_y, 4)],
            "width": round(self.width, 4),
            "height": round(self.height, 4),
            "centroid": [round(c, 4) for c in self.centroid],
            "aspect_ratio": round(self.aspect_ratio, 4),
        }


@dataclass
class RawEntity:
    """
    One geometric entity extracted from the DXF.
    All coordinates are in millimetres.

    Attributes:
        entity_id: Unique string identifier for the entity.
        dxf_type: The DXF entity type (e.g., LINE, LWPOLYLINE).
        layer: The CAD layer name.
        layer_hint: Heuristic structural classification.
        geometry: Dictionary containing entity geometry data.
        bounding_box: BoundingBox object representing the spatial limits.
        attributes: Additional CAD attributes and metadata.
        spatial_hash: Spatial grid key.
        flags: Semantic tags (e.g., void).
        source_handle: Traceable handle to the original DXF entity.
        layout_name: The sheet tab or layout name (default "Model").
    """
    entity_id: str
    dxf_type: str
    layer: str
    layer_hint: str
    geometry: dict[str, Any]
    bounding_box: BoundingBox
    attributes: dict[str, Any] = field(default_factory=dict)
    spatial_hash: str = ""
    flags: list[str] = field(default_factory=list)
    source_handle: str = ""   # ezdxf entity handle for traceability
    layout_name: str = "Model"

    def to_dict(self) -> dict:
        """
        Serialize the raw entity to a dictionary.

        Returns:
            A dictionary representation of the RawEntity.
        """
        return {
            "entity_id": self.entity_id,
            "dxf_type": self.dxf_type,
            "layer": self.layer,
            "layer_hint": self.layer_hint,
            "geometry": self.geometry,
            "bounding_box": self.bounding_box.to_dict(),
            "attributes": self.attributes,
            "spatial_hash": self.spatial_hash,
            "flags": self.flags,
            "source_handle": self.source_handle,
            "layout_name": self.layout_name,
        }



@dataclass
class ExtractionResult:
    """Top-level output of the geometric extractor."""
    source_file: str
    units_raw: int
    units_label: str
    conversion_factor: float
    units_warning: str | None
    layouts_processed: list[str]
    entities: list[RawEntity] = field(default_factory=list)
    layer_map: dict[str, list[str]] = field(default_factory=dict)   # layer → [entity_ids]
    layer_hints: dict[str, str] = field(default_factory=dict)       # layer → hint
    extraction_warnings: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "metadata": {
                "source_file": self.source_file,
                "units_raw": self.units_raw,
                "units_label": self.units_label,
                "conversion_factor": self.conversion_factor,
                "units_warning": self.units_warning,
                "layouts_processed": self.layouts_processed,
            },
            "stats": self.stats,
            "layer_hints": self.layer_hints,
            "layer_map": self.layer_map,
            "extraction_warnings": self.extraction_warnings,
            "entities": [e.to_dict() for e in self.entities],
        }


# ---------------------------------------------------------------------------
# Core extractor
# ---------------------------------------------------------------------------

class DXFGeometricExtractor:
    """
    Parses a DXF file and produces a normalized Raw Geometry JSON payload
    ready for the LangGraph Parser Agent.

    Usage:
        extractor = DXFGeometricExtractor("path/to/drawing.dxf")
        result = extractor.extract()
        raw_json = result.to_dict()
    """

    def __init__(self, filepath: str | Path, target_layout: str | None = None):
        """
        Args:
            filepath:       Path to the DXF file.
            target_layout:  Name of a specific model-space layout to process.
                            If None, all model-space layouts are processed.
        """
        self.filepath = Path(filepath)
        self.target_layout = target_layout
        self._doc: Drawing | None = None
        self._factor: float = 1.0          # unit → mm conversion factor
        self._units_raw: int = 0
        self._warnings: list[str] = []
        self._stats: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self) -> ExtractionResult:
        """Run the full extraction pipeline. Returns ExtractionResult."""
        logger.info("Opening DXF file: %s", self.filepath)
        self._doc = self._open_dxf()

        units_raw, units_label, factor, units_warning = self._resolve_units()
        self._factor = factor
        self._units_raw = units_raw

        if units_warning:
            self._warnings.append(units_warning)
            logger.warning(units_warning)

        layouts = self._select_layouts()
        layout_names = [layout.name for layout in layouts]
        logger.info("Processing layouts: %s", layout_names)

        all_entities: list[RawEntity] = []
        for layout in layouts:
            logger.info("  → Extracting from layout: %s", layout.name)
            layout_entities = self._extract_layout(layout)
            all_entities.extend(layout_entities)

        # Run layout validation to detect and reject side-by-side floor layouts
        self._validate_layout_separation(all_entities)

        # Build layer map and per-layer hints
        layer_map: dict[str, list[str]] = {}
        layer_hints: dict[str, str] = {}
        for ent in all_entities:
            layer_map.setdefault(ent.layer, []).append(ent.entity_id)
            if ent.layer not in layer_hints:
                layer_hints[ent.layer] = ent.layer_hint

        # Stats
        type_counts: dict[str, int] = {}
        hint_counts: dict[str, int] = {}
        for ent in all_entities:
            type_counts[ent.dxf_type] = type_counts.get(ent.dxf_type, 0) + 1
            hint_counts[ent.layer_hint] = hint_counts.get(ent.layer_hint, 0) + 1

        stats = {
            "total_entities": len(all_entities),
            "unique_layers": len(layer_map),
            **{f"type_{k}": v for k, v in sorted(type_counts.items())},
            **{f"hint_{k}": v for k, v in sorted(hint_counts.items())},
        }

        logger.info(
            "Extraction complete. %d entities across %d layers.",
            len(all_entities), len(layer_map),
        )

        return ExtractionResult(
            source_file=str(self.filepath),
            units_raw=units_raw,
            units_label=units_label,
            conversion_factor=factor,
            units_warning=units_warning,
            layouts_processed=layout_names,
            entities=all_entities,
            layer_map=layer_map,
            layer_hints=layer_hints,
            extraction_warnings=self._warnings,
            stats=stats,
        )

    # ------------------------------------------------------------------
    # File loading
    # ------------------------------------------------------------------

    def _open_dxf(self) -> Drawing:
        """Open DXF with encoding fallback for legacy files."""
        try:
            return ezdxf.readfile(str(self.filepath))
        except UnicodeDecodeError:
            logger.warning(
                "UTF-8 decode failed — retrying with latin-1 encoding."
            )
            return ezdxf.readfile(str(self.filepath), encoding="latin-1")
        except ezdxf.DXFError as exc:
            logger.error("Failed to open DXF file: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Unit resolution
    # ------------------------------------------------------------------

    def _resolve_units(self) -> tuple[int, str, float, str | None]:
        """
        Read $INSUNITS from the DXF header and return
        (raw_int, label, mm_factor, warning_or_None).

        Falls back to inference from drawing extents if $INSUNITS is 0
        (unitless), which is common in older structural drawings.
        """
        doc = self._doc
        if doc is None:
            raise ValueError("Document not loaded")

        try:
            raw = int(doc.header.get("$INSUNITS", 0))
        except Exception:
            raw = 0

        factor = INSUNITS_TO_MM.get(raw, 1.0)
        label = units.unit_name(raw) if raw in range(24) else "unknown"
        warning = None

        if raw == 0:
            # Unitless — attempt inference from extents
            inferred_factor, inferred_label = self._infer_units_from_extents(doc)
            warning = (
                f"$INSUNITS is 0 (unitless). Inferred units as "
                f"'{inferred_label}' from drawing extents. "
                f"HUMAN VERIFICATION REQUIRED before any calculations."
            )
            return raw, inferred_label, inferred_factor, warning

        # Cross-validate scale factor against drawing extents to detect unit misalignment
        try:
            extmin_val = doc.header.get("$EXTMIN", (0.0, 0.0, 0.0))
            extmax_val = doc.header.get("$EXTMAX", (0.0, 0.0, 0.0))
            x1 = extmin_val[0] if isinstance(extmin_val, (tuple, list)) else getattr(extmin_val, "x", 0.0)
            x2 = extmax_val[0] if isinstance(extmax_val, (tuple, list)) else getattr(extmax_val, "x", 0.0)
            
            implied_width_m = abs(x2 - x1) * factor / 1000.0
            if implied_width_m > 300.0 and factor > 1.0:
                # CAD template is almost certainly set to Inches/Feet incorrectly
                # while coordinates are actually millimeters. Force override to MM factor.
                logger.warning(
                    f"Scale override triggered: $INSUNITS={raw} ({label}) implies "
                    f"an absurd implied building width of {implied_width_m:.2f} meters. "
                    f"Overriding scale factor to 1.0 (millimeters)."
                )
                warning = (
                    f"$INSUNITS={raw} ({label}) implies an implausible implied width of "
                    f"{implied_width_m:.1f} m. Overriding scale factor to 1.0 (mm)."
                )
                factor = 1.0
                label = "millimetres (overridden)"
        except Exception as err:
            logger.warning(f"Cross-validating drawing extents failed: {err}")

        if factor == 1.0 and raw != 4 and warning is None:
            warning = (
                f"Unrecognised $INSUNITS value {raw}. "
                f"Defaulting conversion factor to 1.0 (treating as mm). "
                f"HUMAN VERIFICATION REQUIRED."
            )

        return raw, label, factor, warning

    def _infer_units_from_extents(self, doc: Drawing) -> tuple[float, str]:
        """
        Heuristic: if the drawing extents suggest a building measured in
        single-digit to low hundreds of values, it's likely in metres.
        If values are in thousands, likely already in mm.

        Args:
            doc: The loaded ezdxf Drawing document object.

        Returns:
            A tuple of (conversion_factor_to_mm, unit_label_string).
        """
        extmin = doc.header.get("$EXTMIN", Vec3(0, 0, 0))
        extmax = doc.header.get("$EXTMAX", Vec3(0, 0, 0))

        width = abs(extmax.x - extmin.x)
        height = abs(extmax.y - extmin.y)
        max_dim = max(width, height)

        # A typical building plan:
        # In metres:      10 – 200   (residential to large commercial)
        # In mm:      10000 – 200000
        # In cm:       1000 – 20000

        if max_dim < 1:
            return INSUNITS_TO_MM[6], "metres (inferred — very small extents)"
        elif max_dim < 500:
            return INSUNITS_TO_MM[6], "metres (inferred)"
        elif max_dim < 5000:
            return INSUNITS_TO_MM[5], "centimetres (inferred)"
        else:
            return INSUNITS_TO_MM[4], "millimetres (inferred)"

    # ------------------------------------------------------------------
    # Layout selection
    # ------------------------------------------------------------------

    def _select_layouts(self) -> list[Layout]:
        """
        Return a list of layouts to process.
        Structural drawings often have multiple model-space layouts
        (e.g., Ground Floor, First Floor, Roof).
        """
        doc = self._doc
        if doc is None:
            raise ValueError("Document not loaded")

        layouts: list[Layout] = []

        if self.target_layout:
            try:
                layouts.append(doc.layouts.get(self.target_layout))
            except ezdxf.DXFKeyError:
                logger.warning(
                    "Layout '%s' not found. Falling back to modelspace.",
                    self.target_layout,
                )
                layouts.append(doc.modelspace())
        else:
            # Process modelspace by default
            layouts.append(doc.modelspace())
            # Include any additional layouts (model space or paper space sheets) containing structural data
            for layout in doc.layouts:
                if layout.name in ("Model", "*Model_Space"):
                    continue
                
                # If it's a paperspace layout, check if it contains structural entities
                # to avoid processing empty template layouts like Layout1/Layout2.
                if layout.is_any_paperspace:
                    has_structural_ents = False
                    for ent in layout:
                        layer = ent.dxf.layer.lower() if hasattr(ent, "dxf") and hasattr(ent.dxf, "layer") else ""
                        if any(keyword in layer for keyword in ("beam", "column", "col", "slab", "wall")):
                            has_structural_ents = True
                            break
                    if not has_structural_ents:
                        continue

                layouts.append(layout)
                logger.info("Found additional layout: %s", layout.name)

        return layouts

    def _validate_layout_separation(self, entities: list[RawEntity]) -> None:
        """
        Validate that the drawing does not contain multiple floor plans
        drawn side-by-side or stacked vertically in a single layout sheet.

        Heuristic:
        1. Find any floor/plan titles (e.g., 'GROUND FLOOR PLAN', 'FIRST FLOOR').
        2. If multiple distinct floor titles are present and horizontally/vertically
           separated by > 15m, raise a validation error.
        3. As a fallback, if a single layout tab has a spatial gap > 15m in structural members
           with at least 5 members on each side, reject it.

        Args:
            entities: List of extracted RawEntity instances.

        Raises:
            ValueError: If multiple plans are detected side-by-side or stacked.
        """
        from collections import defaultdict
        entities_by_layout = defaultdict(list)
        for ent in entities:
            entities_by_layout[ent.layout_name].append(ent)

        for layout_name, layout_ents in entities_by_layout.items():
            # 1. Look for floor plan titles
            floor_titles = []
            for ent in layout_ents:
                if ent.dxf_type in ("TEXT", "MTEXT") and "text_content" in ent.attributes:
                    text_content = ent.attributes.get("text_content")
                    if text_content:
                        text_upper = text_content.strip().upper()
                        # Match words like GROUND FLOOR, FIRST FLOOR, 1ST FLOOR, ROOF PLAN
                        if re.search(
                            r"\b(GROUND|FIRST|SECOND|THIRD|FOURTH|FIFTH|ROOF|1ST|2ND|3RD|4TH|5TH|TYPICAL)\s+(FLOOR|PLAN|LAYOUT)\b",
                            text_upper
                        ):
                            floor_titles.append(ent)

            # Check if there are multiple unique floor titles separated by a significant distance
            if len(floor_titles) >= 2:
                # Find distinct labels (skip exact duplicates within small proximity)
                unique_titles: list[RawEntity] = []
                for title in floor_titles:
                    text_content = title.attributes.get("text_content")
                    if not text_content:
                        continue
                    text = text_content.strip().upper()
                    # Check if this title is too close to an already registered title of the same content
                    if not any(
                        t.attributes.get("text_content", "").strip().upper() == text
                        and math.hypot(
                            t.bounding_box.centroid[0] - title.bounding_box.centroid[0],
                            t.bounding_box.centroid[1] - title.bounding_box.centroid[1]
                        ) < 5000.0  # 5m proximity threshold
                        for t in unique_titles
                    ):
                        unique_titles.append(title)

                if len(unique_titles) >= 2:
                    # Check if any two distinct titles are separated horizontally or vertically by > 15m
                    for idx, t1 in enumerate(unique_titles):
                        for t2 in unique_titles[idx+1:]:
                            c1 = t1.bounding_box.centroid
                            c2 = t2.bounding_box.centroid
                            dx = abs(c1[0] - c2[0])
                            dy = abs(c1[1] - c2[1])
                            if dx > 15000.0 or dy > 15000.0:
                                t1_text = t1.attributes.get("text_content", "Unknown")
                                t2_text = t2.attributes.get("text_content", "Unknown")
                                raise ValueError(
                                    "INVALID_LAYOUT_STRUCTURE: Multiple plans detected side-by-side or stacked in Model space or layout "
                                    f"'{layout_name}' (Titles found: '{t1_text}' and '{t2_text}'). "
                                    "Please arrange each floor layout in a separate sheet/tab."
                                )

            # 2. Fallback: Structural member density spatial gap check
            structural_candidates = [
                ent for ent in layout_ents
                if ent.layer_hint in ("beam_candidate", "column_candidate", "slab_candidate")
                or any(keyword in ent.layer.lower() for keyword in ("beam", "column", "col", "slab", "wall"))
            ]
            if len(structural_candidates) < 15:
                continue

            # Check horizontal gaps
            x_coords = sorted(ent.bounding_box.centroid[0] for ent in structural_candidates)
            for i in range(len(x_coords) - 1):
                gap = x_coords[i+1] - x_coords[i]
                if gap > 15000.0:  # 15 meters
                    left_count = sum(1 for x in x_coords if x <= x_coords[i])
                    right_count = sum(1 for x in x_coords if x >= x_coords[i+1])
                    if left_count >= 5 and right_count >= 5:
                        raise ValueError(
                            "INVALID_LAYOUT_STRUCTURE: Multiple plans detected side-by-side in Model space or layout "
                            f"'{layout_name}'. Please arrange each floor layout in a separate sheet/tab."
                        )

            # Check vertical gaps
            y_coords = sorted(ent.bounding_box.centroid[1] for ent in structural_candidates)
            for i in range(len(y_coords) - 1):
                gap = y_coords[i+1] - y_coords[i]
                if gap > 15000.0:  # 15 meters
                    bottom_count = sum(1 for y in y_coords if y <= y_coords[i])
                    top_count = sum(1 for y in y_coords if y >= y_coords[i+1])
                    if bottom_count >= 5 and top_count >= 5:
                        raise ValueError(
                            "INVALID_LAYOUT_STRUCTURE: Multiple plans detected side-by-side/stacked in Model space or layout "
                            f"'{layout_name}'. Please arrange each floor layout in a separate sheet/tab."
                        )

    # ------------------------------------------------------------------
    # Per-layout extraction
    # ------------------------------------------------------------------

    def _extract_layout(self, layout: Layout) -> list[RawEntity]:
        """Extract all supported entities from a single layout."""
        entities: list[RawEntity] = []

        for dxf_entity in layout:
            try:
                extracted = self._dispatch_entity(dxf_entity)
                if extracted:
                    for ent in extracted:
                        ent.layout_name = layout.name
                    entities.extend(extracted)
            except Exception as exc:
                handle = getattr(dxf_entity, "dxf", None)
                handle_str = getattr(handle, "handle", "unknown") if handle else "unknown"
                self._warnings.append(
                    f"Failed to process entity (handle={handle_str}, "
                    f"type={dxf_entity.dxftype()}): {exc}"
                )
                logger.debug("Entity processing error: %s", exc, exc_info=True)

        return entities

    # ------------------------------------------------------------------
    # Entity dispatcher
    # ------------------------------------------------------------------

    def _dispatch_entity(self, entity: DXFGraphic) -> list[RawEntity] | None:
        """Route each DXF entity type to the correct extraction method."""
        etype = entity.dxftype()

        dispatch: dict[str, Any] = {
            "LINE":       self._extract_line,
            "LWPOLYLINE": self._extract_lwpolyline,
            "POLYLINE":   self._extract_polyline,
            "SPLINE":     self._extract_spline,
            "CIRCLE":     self._extract_circle,
            "ARC":        self._extract_arc,
            "ELLIPSE":    self._extract_ellipse,
            "INSERT":     self._extract_insert,
            "TEXT":       self._extract_text,
            "MTEXT":      self._extract_mtext,
            "DIMENSION":  self._extract_dimension,
            "SOLID":      self._extract_solid,
            "TRACE":      self._extract_solid,   # TRACE is identical to SOLID
            "HATCH":      self._extract_hatch,
            "POINT":      self._extract_point,
        }

        handler = dispatch.get(etype)
        if handler:
            return handler(entity)

        # Silently skip known non-geometric types
        silent_skip = {
            "VIEWPORT", "OLE2FRAME", "IMAGE", "WIPEOUT",
            "ACAD_PROXY_ENTITY", "BODY", "REGION", "3DSOLID",
        }
        if etype not in silent_skip:
            logger.debug("Unsupported entity type skipped: %s", etype)

        return None

    # ------------------------------------------------------------------
    # LINE
    # Structural engineers frequently draw beams and columns as single
    # centre-lines, especially in preliminary or schematic drawings.
    # ------------------------------------------------------------------

    def _extract_line(self, entity: Line) -> list[RawEntity] | None:
        start = self._to_mm_2d(entity.dxf.start)
        end = self._to_mm_2d(entity.dxf.end)

        length = math.hypot(end[0] - start[0], end[1] - start[1])
        if length < MIN_MEMBER_LENGTH_MM:
            return None   # Likely a hatch or dimension tick — skip

        angle = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
        # Normalise angle to [0, 180)
        if angle < 0:
            angle += 180.0

        bbox = self._bbox_from_points([start, end])

        geometry = {
            "start": list(start),
            "end": list(end),
            "length": round(length, 4),
            "angle_deg": round(angle, 4),
            "orientation": self._classify_orientation(angle),
        }

        return [self._build_entity(entity, "LINE", geometry, bbox)]

    # ------------------------------------------------------------------
    # LWPOLYLINE
    # Used for beam/column outlines (closed), slab edges, wall runs.
    # A closed LWPOLYLINE with 4 vertices is the most common way
    # structural engineers draw a column or beam cross-section in plan.
    # ------------------------------------------------------------------

    def _extract_lwpolyline(self, entity: LWPolyline) -> list[RawEntity] | None:
        pts_raw = list(entity.get_points())   # (x, y, start_width, end_width, bulge)
        if not pts_raw:
            return None

        vertices_mm = [self._to_mm_2d((p[0], p[1])) for p in pts_raw]
        is_closed = entity.closed
        has_bulge = any(abs(p[4]) > 1e-6 for p in pts_raw if len(p) > 4)

        if is_closed:
            perimeter = self._polyline_perimeter(vertices_mm, closed=True)
            area = self._polygon_area(vertices_mm)
        else:
            perimeter = self._polyline_perimeter(vertices_mm, closed=False)
            area = None

        bbox = self._bbox_from_points(vertices_mm)

        # Filter out hatch-line clutter: very short open polylines
        if not is_closed and perimeter < MIN_MEMBER_LENGTH_MM:
            return None

        # Dominant angle — angle of the longest segment
        dominant_angle = self._dominant_angle(vertices_mm, is_closed)

        geometry = {
            "vertices": [list(v) for v in vertices_mm],
            "is_closed": is_closed,
            "has_arc_segments": has_bulge,
            "vertex_count": len(vertices_mm),
            "perimeter": round(perimeter, 4),
            "area_mm2": round(area, 4) if area is not None else None,
            "dominant_angle_deg": round(dominant_angle, 4),
            "orientation": self._classify_orientation(dominant_angle),
        }

        ent = self._build_entity(entity, "LWPOLYLINE", geometry, bbox)

        # Flag rectangular closed polylines — likely section outlines
        if is_closed and len(vertices_mm) == 4:
            ent.flags.append("rectangular_outline")
        if is_closed and len(vertices_mm) > 4:
            ent.flags.append("complex_outline")

        return [ent]

    # ------------------------------------------------------------------
    # POLYLINE (legacy 3D/2D polyline)
    # Older AutoCAD versions and some structural software output POLYLINE
    # instead of LWPOLYLINE. Also handles 3D polylines.
    # ------------------------------------------------------------------

    def _extract_polyline(self, entity: Polyline) -> list[RawEntity] | None:
        # Flatten 3D vertices to 2D
        vertices_raw = [v.dxf.location for v in entity.vertices]
        if not vertices_raw:
            return None

        vertices_mm = [self._to_mm_2d((v.x, v.y)) for v in vertices_raw]
        is_closed = entity.is_closed

        if not is_closed and len(vertices_mm) < 2:
            return None

        perimeter = self._polyline_perimeter(vertices_mm, closed=is_closed)
        area = self._polygon_area(vertices_mm) if is_closed else None

        if not is_closed and perimeter < MIN_MEMBER_LENGTH_MM:
            return None

        bbox = self._bbox_from_points(vertices_mm)
        dominant_angle = self._dominant_angle(vertices_mm, is_closed)

        geometry = {
            "vertices": [list(v) for v in vertices_mm],
            "is_closed": is_closed,
            "vertex_count": len(vertices_mm),
            "perimeter": round(perimeter, 4),
            "area_mm2": round(area, 4) if area is not None else None,
            "dominant_angle_deg": round(dominant_angle, 4),
            "orientation": self._classify_orientation(dominant_angle),
        }

        ent = self._build_entity(entity, "POLYLINE", geometry, bbox)
        if is_closed and len(vertices_mm) == 4:
            ent.flags.append("rectangular_outline")

        return [ent]

    # ------------------------------------------------------------------
    # SPLINE
    # Occasionally used for curved ramps, arched beams, or plot borders.
    # We approximate with evenly sampled points along the curve.
    # ------------------------------------------------------------------

    def _extract_spline(self, entity: Spline) -> list[RawEntity] | None:
        try:
            # Sample 32 points along the spline for approximation
            approx_pts = list(entity.flattening(0.01, segments=32))
        except Exception:
            approx_pts = []

        if len(approx_pts) < 2:
            return None

        vertices_mm = [self._to_mm_2d((p.x, p.y)) for p in approx_pts]
        bbox = self._bbox_from_points(vertices_mm)
        perimeter = self._polyline_perimeter(vertices_mm, closed=False)

        if perimeter < MIN_MEMBER_LENGTH_MM:
            return None

        geometry = {
            "vertices": [list(v) for v in vertices_mm],
            "is_closed": entity.closed,
            "vertex_count": len(vertices_mm),
            "perimeter": round(perimeter, 4),
            "approximation": "flattened_spline",
        }

        ent = self._build_entity(entity, "SPLINE", geometry, bbox)
        ent.flags.append("approximated_curve")
        return [ent]

    # ------------------------------------------------------------------
    # CIRCLE
    # Circular columns, auger piles, holes in slabs.
    # ------------------------------------------------------------------

    def _extract_circle(self, entity: Circle) -> list[RawEntity] | None:
        centre = self._to_mm_2d(entity.dxf.center)
        radius = float(entity.dxf.radius) * self._factor
        diameter = radius * 2.0

        if diameter < MIN_MEMBER_LENGTH_MM:
            return None   # Too small — likely a bolt hole or detail marker

        bbox = BoundingBox(
            min_x=centre[0] - radius,
            min_y=centre[1] - radius,
            max_x=centre[0] + radius,
            max_y=centre[1] + radius,
        )

        geometry = {
            "centre": list(centre),
            "radius": round(radius, 4),
            "diameter": round(diameter, 4),
            "area_mm2": round(math.pi * radius ** 2, 4),
        }

        ent = self._build_entity(entity, "CIRCLE", geometry, bbox)
        ent.flags.append("circular_section")
        return [ent]

    # ------------------------------------------------------------------
    # ARC
    # Curved beams, arch structures, or detail callout arcs.
    # ------------------------------------------------------------------

    def _extract_arc(self, entity: Arc) -> list[RawEntity] | None:
        centre = self._to_mm_2d(entity.dxf.center)
        radius = float(entity.dxf.radius) * self._factor
        start_angle = float(entity.dxf.start_angle)
        end_angle = float(entity.dxf.end_angle)

        # Arc length
        delta = end_angle - start_angle
        if delta <= 0:
            delta += 360.0
        arc_length = radius * math.radians(delta)

        if arc_length < MIN_MEMBER_LENGTH_MM:
            return None

        # Bounding box of the arc chord + sagitta
        start_pt = (
            centre[0] + radius * math.cos(math.radians(start_angle)),
            centre[1] + radius * math.sin(math.radians(start_angle)),
        )
        end_pt = (
            centre[0] + radius * math.cos(math.radians(end_angle)),
            centre[1] + radius * math.sin(math.radians(end_angle)),
        )

        # Sample arc for bbox (catch extremes at 0/90/180/270 if within arc)
        sample_pts = [start_pt, end_pt]
        for cardinal in (0.0, 90.0, 180.0, 270.0):
            ang = start_angle if start_angle < end_angle else start_angle - 360.0
            if ang <= cardinal <= end_angle:
                sample_pts.append((
                    centre[0] + radius * math.cos(math.radians(cardinal)),
                    centre[1] + radius * math.sin(math.radians(cardinal)),
                ))
        bbox = self._bbox_from_points(sample_pts)

        geometry = {
            "centre": list(centre),
            "radius": round(radius, 4),
            "start_angle_deg": round(start_angle, 4),
            "end_angle_deg": round(end_angle, 4),
            "arc_length": round(arc_length, 4),
            "start_point": [round(start_pt[0], 4), round(start_pt[1], 4)],
            "end_point": [round(end_pt[0], 4), round(end_pt[1], 4)],
        }

        return [self._build_entity(entity, "ARC", geometry, bbox)]

    # ------------------------------------------------------------------
    # ELLIPSE
    # Occasionally used for oval columns or architectural features.
    # ------------------------------------------------------------------

    def _extract_ellipse(self, entity) -> list[RawEntity] | None:
        try:
            centre = self._to_mm_2d(entity.dxf.center)
            major_axis = entity.dxf.major_axis
            ratio = float(entity.dxf.ratio)   # minor/major

            major_len = math.hypot(major_axis.x, major_axis.y) * self._factor
            minor_len = major_len * ratio

            bbox = BoundingBox(
                min_x=centre[0] - major_len,
                min_y=centre[1] - minor_len,
                max_x=centre[0] + major_len,
                max_y=centre[1] + minor_len,
            )

            geometry = {
                "centre": list(centre),
                "major_axis_length": round(major_len, 4),
                "minor_axis_length": round(minor_len, 4),
                "ratio": round(ratio, 4),
            }

            ent = self._build_entity(entity, "ELLIPSE", geometry, bbox)
            ent.flags.append("elliptical_section")
            return [ent]
        except Exception:
            return None

    # ------------------------------------------------------------------
    # INSERT (Block Reference)
    # The most complex case. Structural engineers use blocks extensively:
    #   - Column grids (circle + cross + label)
    #   - Section markers (arrow + circle + letter)
    #   - Standard section symbols (UC/UB steel profiles)
    #   - Title block frames
    #   - North arrows, scale bars
    #
    # Strategy: explode into virtual sub-entities + extract block metadata.
    # ------------------------------------------------------------------

    def _extract_insert(self, entity: Insert) -> list[RawEntity] | None:
        results: list[RawEntity] = []

        block_name = entity.dxf.name
        insertion = self._to_mm_2d(entity.dxf.insert)
        x_scale = getattr(entity.dxf, "xscale", 1.0)
        y_scale = getattr(entity.dxf, "yscale", 1.0)
        rotation = getattr(entity.dxf, "rotation", 0.0)

        # Extract block attributes (labels like "C1", "B2", "G1")
        attrib_values: dict[str, str] = {}
        for attrib in entity.attribs:
            tag = attrib.dxf.tag.upper().strip()
            value = attrib.dxf.text.strip()
            attrib_values[tag] = value

        # Classify the block by its name
        block_hint = self._classify_block_name(block_name)

        # Bounding box from virtual entities
        sub_points: list[tuple[float, float]] = [insertion]

        # Explode block into constituent virtual entities
        try:
            for sub_entity in entity.virtual_entities():
                sub_type = sub_entity.dxftype()

                if sub_type == "LINE" and isinstance(sub_entity, Line):
                    p1 = self._to_mm_2d(sub_entity.dxf.start)
                    p2 = self._to_mm_2d(sub_entity.dxf.end)
                    sub_points.extend([p1, p2])

                elif sub_type == "LWPOLYLINE" and isinstance(sub_entity, LWPolyline):
                    for pt in sub_entity.get_points():
                        sub_points.append(self._to_mm_2d((pt[0], pt[1])))

                elif sub_type == "CIRCLE" and isinstance(sub_entity, Circle):
                    c = self._to_mm_2d(sub_entity.dxf.center)
                    r = float(sub_entity.dxf.radius) * self._factor
                    sub_points.extend([
                        (c[0] - r, c[1] - r),
                        (c[0] + r, c[1] + r),
                    ])

        except Exception as exc:
            self._warnings.append(
                f"Could not explode block '{block_name}': {exc}"
            )

        bbox = self._bbox_from_points(sub_points) if len(sub_points) > 1 else \
               BoundingBox(insertion[0], insertion[1], insertion[0], insertion[1])

        geometry = {
            "insertion_point": list(insertion),
            "block_name": block_name,
            "x_scale": round(x_scale, 6),
            "y_scale": round(y_scale, 6),
            "rotation_deg": round(rotation, 4),
        }

        attributes = {
            "block_hint": block_hint,
            "attrib_values": attrib_values,
        }

        # Extract any text labels directly from the attributes
        if attrib_values:
            # Prioritise common label tags
            for tag in ("LABEL", "TAG", "MARK", "ID", "NAME", "NO"):
                if tag in attrib_values:
                    attributes["member_label"] = attrib_values[tag]
                    break

        ent = self._build_entity(entity, "INSERT", geometry, bbox, attributes)
        ent.layer_hint = block_hint if block_hint != "unknown_block" else ent.layer_hint
        results.append(ent)

        return results

    # ------------------------------------------------------------------
    # TEXT / MTEXT
    # Member labels, grid references, section callouts, dimension text.
    # Essential for the agent to associate labels with members.
    # ------------------------------------------------------------------

    def _extract_text(self, entity: Text) -> list[RawEntity] | None:
        content = entity.dxf.text.strip()
        if not content:
            return None

        insert = self._to_mm_2d(entity.dxf.insert)
        height = float(entity.dxf.height) * self._factor
        rotation = getattr(entity.dxf, "rotation", 0.0)

        # Approximate bbox from text height (width ≈ 0.6 × height × char_count)
        approx_width = height * 0.6 * len(content)
        bbox = BoundingBox(
            min_x=insert[0],
            min_y=insert[1],
            max_x=insert[0] + approx_width,
            max_y=insert[1] + height,
        )

        geometry = {
            "insertion_point": list(insert),
            "text_height": round(height, 4),
            "rotation_deg": round(rotation, 4),
        }

        attributes = {
            "text_content": content,
            "text_type": self._classify_text(content),
        }

        return [self._build_entity(entity, "TEXT", geometry, bbox, attributes)]

    def _extract_mtext(self, entity: MText) -> list[RawEntity] | None:
        raw_text = entity.plain_text(split=False)
        if isinstance(raw_text, list):
            content = "\n".join(raw_text).strip()
        else:
            content = raw_text.strip()
        if not content:
            return None

        insert = self._to_mm_2d(entity.dxf.insert)
        char_height = float(entity.dxf.char_height) * self._factor

        try:
            width = float(entity.dxf.width) * self._factor
        except Exception:
            width = char_height * 0.6 * len(content)

        bbox = BoundingBox(
            min_x=insert[0],
            min_y=insert[1],
            max_x=insert[0] + width,
            max_y=insert[1] + char_height,
        )

        geometry = {
            "insertion_point": list(insert),
            "char_height": round(char_height, 4),
            "width": round(width, 4),
        }

        attributes = {
            "text_content": content,
            "text_type": self._classify_text(content),
        }

        return [self._build_entity(entity, "MTEXT", geometry, bbox, attributes)]

    # ------------------------------------------------------------------
    # DIMENSION
    # Annotated dimensions — carries the measured value and endpoints.
    # Useful for the agent to cross-check geometric dimensions.
    # ------------------------------------------------------------------

    def _extract_dimension(self, entity) -> list[RawEntity] | None:
        try:
            defpt = self._to_mm_2d(entity.dxf.defpoint)
            text_midpt = self._to_mm_2d(entity.dxf.text_midpoint) \
                if hasattr(entity.dxf, "text_midpoint") else defpt

            dim_text = getattr(entity.dxf, "text", "<>").strip()
            dim_value = getattr(entity.dxf, "actual_measurement", None)

            bbox = self._bbox_from_points([defpt, text_midpt])

            geometry = {
                "definition_point": list(defpt),
                "text_midpoint": list(text_midpt),
            }

            attributes = {
                "text_content": dim_text,
                "actual_measurement_mm": round(float(dim_value) * self._factor, 4)
                    if dim_value is not None else None,
                "text_type": "dimension",
            }

            ent = self._build_entity(entity, "DIMENSION", geometry, bbox, attributes)
            ent.flags.append("dimension_entity")
            return [ent]
        except Exception:
            return None

    # ------------------------------------------------------------------
    # SOLID / TRACE
    # Used for filled sections, structural shading, or thick walls.
    # ------------------------------------------------------------------

    def _extract_solid(self, entity) -> list[RawEntity] | None:
        try:
            # SOLID has 4 corner points (p1..p4)
            pts = [
                self._to_mm_2d(entity.dxf.vtx0),
                self._to_mm_2d(entity.dxf.vtx1),
                self._to_mm_2d(entity.dxf.vtx2),
                self._to_mm_2d(entity.dxf.vtx3),
            ]
            bbox = self._bbox_from_points(pts)
            area = self._polygon_area(pts)

            geometry = {
                "vertices": [list(p) for p in pts],
                "area_mm2": round(area, 4),
            }

            ent = self._build_entity(entity, entity.dxftype(), geometry, bbox)
            ent.flags.append("filled_region")
            return [ent]
        except Exception:
            return None

    # ------------------------------------------------------------------
    # HATCH
    # Concrete fill patterns, section hatching.
    # Extract the outer boundary only — the fill pattern lines are noise.
    # ------------------------------------------------------------------

    def _extract_hatch(self, entity) -> list[RawEntity] | None:
        try:
            boundary_pts: list[tuple[float, float]] = []

            for path in entity.paths:
                path_type = path.PATH_TYPE

                if path_type == "EdgePath":
                    for edge in path.edges:
                        edge_type = edge.EDGE_TYPE
                        if edge_type == "LineEdge":
                            boundary_pts.append(self._to_mm_2d(edge.start))
                            boundary_pts.append(self._to_mm_2d(edge.end))
                        elif edge_type == "ArcEdge":
                            boundary_pts.append(self._to_mm_2d(edge.center))
                elif path_type == "PolylinePath":
                    for v in path.vertices:
                        boundary_pts.append(self._to_mm_2d((v.x, v.y)))

            if not boundary_pts:
                return None

            bbox = self._bbox_from_points(boundary_pts)

            # Ignore very small hatches (dimension arrowheads etc.)
            if bbox.width < MIN_MEMBER_LENGTH_MM and bbox.height < MIN_MEMBER_LENGTH_MM:
                return None

            area = bbox.width * bbox.height   # approximate
            pattern = getattr(entity.dxf, "pattern_name", "UNKNOWN")

            geometry = {
                "boundary_points": [list(p) for p in boundary_pts],
                "approximate_area_mm2": round(area, 4),
            }

            attributes = {
                "hatch_pattern": pattern,
                "is_concrete_hatch": self._is_concrete_pattern(pattern),
            }

            ent = self._build_entity(entity, "HATCH", geometry, bbox, attributes)
            ent.flags.append("hatch_boundary")
            return [ent]
        except Exception:
            return None

    # ------------------------------------------------------------------
    # POINT
    # Column grid intersection markers.
    # ------------------------------------------------------------------

    def _extract_point(self, entity) -> list[RawEntity] | None:
        pt = self._to_mm_2d(entity.dxf.location)
        bbox = BoundingBox(pt[0], pt[1], pt[0], pt[1])
        geometry = {"point": list(pt)}
        ent = self._build_entity(entity, "POINT", geometry, bbox)
        ent.flags.append("point_marker")
        return [ent]

    # ------------------------------------------------------------------
    # Entity builder — shared finalisation logic
    # ------------------------------------------------------------------

    def _build_entity(
        self,
        dxf_ent: DXFGraphic,
        dxf_type: str,
        geometry: dict,
        bbox: BoundingBox,
        attributes: dict | None = None,
    ) -> RawEntity:
        layer = self._safe_layer(dxf_ent)
        layer_hint = self._classify_layer(layer)
        centroid = bbox.centroid
        spatial_hash = self._spatial_hash(centroid[0], centroid[1])
        handle = getattr(dxf_ent.dxf, "handle", "") or ""

        return RawEntity(
            entity_id=str(uuid.uuid4()),
            dxf_type=dxf_type,
            layer=layer,
            layer_hint=layer_hint,
            geometry=geometry,
            bounding_box=bbox,
            attributes=attributes or {},
            spatial_hash=spatial_hash,
            flags=[],
            source_handle=handle,
        )

    # ------------------------------------------------------------------
    # Classification helpers
    # ------------------------------------------------------------------

    def _classify_layer(self, layer_name: str) -> str:
        """Match layer name against hint patterns. Returns hint string."""
        for pattern, hint in _COMPILED_LAYER_PATTERNS:
            if pattern.search(layer_name):
                return hint
        return "unclassified"

    def _classify_block_name(self, block_name: str) -> str:
        """
        Infer member type from block name.
        Engineers embed the member type in block names, e.g.:
        COL_300x300, UC203x203x60, B_450x300, SECT_A
        """
        bn = block_name.upper()

        col_patterns = [r"COL", r"^C\d", r"PILLAR", r"PILE", r"UC\d", r"CHS\d", r"SHS\d"]
        beam_patterns = [r"BEAM", r"^B\d", r"UB\d", r"^RB\d", r"RSJ", r"LINTEL"]
        slab_patterns = [r"SLAB", r"^S\d", r"FLOOR", r"DECK"]
        grid_patterns = [r"GRID", r"GRIDBALL", r"GRIDSYMBOL", r"COLREF"]
        section_patterns = [r"SECT", r"DETAIL", r"SECTION", r"CALLOUT"]

        for pat in col_patterns:
            if re.search(pat, bn):
                return "column_candidate"
        for pat in beam_patterns:
            if re.search(pat, bn):
                return "beam_candidate"
        for pat in slab_patterns:
            if re.search(pat, bn):
                return "slab_candidate"
        for pat in grid_patterns:
            if re.search(pat, bn):
                return "grid_line"
        for pat in section_patterns:
            if re.search(pat, bn):
                return "dimension_annotation"

        return "unknown_block"

    def _classify_text(self, content: str) -> str:
        """
        Classify a text string's likely role in a structural drawing.
        """
        c = content.strip().upper()

        # Member labels: C1, B2, S1a, G1, etc.
        if re.match(r"^[CBSGFPW]\d{1,3}[A-Z]?$", c):
            return "member_label"

        # Grid references: A, B, 1, 2, AA etc.
        if re.match(r"^([A-Z]{1,2}|\d{1,3})$", c):
            return "grid_reference"

        # Dimension values: 3000, 3000mm, 3.0m, 300x600 etc.
        if re.match(r"^\d+(\.\d+)?\s*(MM|M|CM)?$", c):
            return "dimension_value"
        if re.match(r"^\d+\s*[Xx]\s*\d+", c):
            return "section_dimension"

        # Reinforcement: T16@200, 3T20, H16-200, 8R10 etc.
        if re.match(r"^\d*[THRYBF]\d{1,2}[@\-]?\d*", c):
            return "rebar_label"

        # Level / RL annotations
        if re.match(r"^(RL|FL|FFL|GL|TOS)\s*[+\-]?\s*\d", c):
            return "level_annotation"

        # Load annotations
        if re.match(r"^\d+(\.\d+)?\s*(KN|KPA|KNM|KN/M)", c):
            return "load_annotation"

        return "general_annotation"

    def _classify_orientation(self, angle_deg: float) -> str:
        """
        Classify an angle (0–180°) into a structural orientation.
        Engineers draw horizontal beams (≈0°) and vertical columns (≈90°).
        """
        a = angle_deg % 180.0
        if a < 15.0 or a >= 165.0:
            return "horizontal"
        elif 75.0 <= a < 105.0:
            return "vertical"
        else:
            return "diagonal"

    @staticmethod
    def _is_concrete_pattern(pattern_name: str) -> bool:
        concrete_patterns = {
            "ANSI31", "ANSI32", "AR-CONC", "CONCRETE",
            "DOTS", "NET", "NET3", "GRAVEL",
        }
        return pattern_name.upper() in concrete_patterns

    # ------------------------------------------------------------------
    # Geometric utilities
    # ------------------------------------------------------------------

    def _to_mm_2d(self, point: Any) -> tuple[float, float]:
        """Convert any 2D/3D point to millimetre (x, y) tuple."""
        if hasattr(point, "x"):
            return (float(point.x) * self._factor, float(point.y) * self._factor)
        return (float(point[0]) * self._factor, float(point[1]) * self._factor)

    @staticmethod
    def _bbox_from_points(points: list[tuple[float, float]]) -> BoundingBox:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return BoundingBox(min(xs), min(ys), max(xs), max(ys))

    @staticmethod
    def _polyline_perimeter(
        vertices: list[tuple[float, float]], closed: bool
    ) -> float:
        total = 0.0
        for i in range(len(vertices) - 1):
            dx = vertices[i + 1][0] - vertices[i][0]
            dy = vertices[i + 1][1] - vertices[i][1]
            total += math.hypot(dx, dy)
        if closed and len(vertices) > 1:
            dx = vertices[0][0] - vertices[-1][0]
            dy = vertices[0][1] - vertices[-1][1]
            total += math.hypot(dx, dy)
        return total

    @staticmethod
    def _polygon_area(vertices: list[tuple[float, float]]) -> float:
        """Shoelace formula for polygon area."""
        n = len(vertices)
        if n < 3:
            return 0.0
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += vertices[i][0] * vertices[j][1]
            area -= vertices[j][0] * vertices[i][1]
        return abs(area) / 2.0

    @staticmethod
    def _dominant_angle(
        vertices: list[tuple[float, float]], closed: bool
    ) -> float:
        """Return the angle (0–180°) of the longest segment in a polyline."""
        max_len = -1.0
        dominant = 0.0
        segs = list(range(len(vertices) - 1))
        if closed:
            segs.append(len(vertices) - 1)

        for i in segs:
            j = (i + 1) % len(vertices)
            dx = vertices[j][0] - vertices[i][0]
            dy = vertices[j][1] - vertices[i][1]
            seg_len = math.hypot(dx, dy)
            if seg_len > max_len:
                max_len = seg_len
                ang = math.degrees(math.atan2(dy, dx)) % 180.0
                dominant = ang

        return dominant

    def _spatial_hash(self, x: float, y: float) -> str:
        """
        Assign entities to a spatial grid cell.
        Adjacent entities in the same cell may represent the same structural
        member drawn with multiple overlapping entities.
        """
        cell_x = int(x // SPATIAL_HASH_CELL_MM)
        cell_y = int(y // SPATIAL_HASH_CELL_MM)
        return f"{cell_x}:{cell_y}"

    @staticmethod
    def _safe_layer(entity: DXFGraphic) -> str:
        """Safely retrieve layer name; fall back to '0' (AutoCAD default)."""
        try:
            return entity.dxf.layer or "0"
        except Exception:
            return "0"


# ---------------------------------------------------------------------------
# Convenience function — entry point for FastAPI / LangGraph
# ---------------------------------------------------------------------------

def extract_geometry(
    filepath: str | Path,
    target_layout: str | None = None,
) -> dict:
    """
    Top-level entry point. Returns the Raw Geometry JSON as a plain dict,
    ready to be serialised by FastAPI (json.dumps / jsonable_encoder).

    Args:
        filepath:       Path to the DXF file.
        target_layout:  Optional specific layout name to parse.

    Returns:
        Raw Geometry JSON dict.

    Raises:
        FileNotFoundError: If the DXF file does not exist.
        ezdxf.DXFError:    If the file cannot be parsed.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"DXF file not found: {path}")

    extractor = DXFGeometricExtractor(path, target_layout=target_layout)
    result = extractor.extract()
    return result.to_dict()

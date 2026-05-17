"""
core/parsing/pdf_parser.py
==========================
PDF structural drawing parser.

PDF files do not carry machine-readable geometry; they contain rasterised
images and text annotations.  This module extracts text content and attempts
to infer member data from common schedule/table formats.

Strategy
--------
1. Extract all text blocks using ``pymupdf`` (fitz).
2. Search for known keywords (BEAM, COLUMN, etc.) and associated values.
3. Build member stubs from matched text fragments.
4. Set ``parse_warnings`` to inform the engineer that PDF results require
   manual verification.

Fallback
--------
If ``pymupdf`` is not installed the function returns a minimal response with a
parse warning so the pipeline is not blocked — the engineer is prompted to
supply a DXF file instead.

Dependencies (optional)
-----------------------
``pymupdf`` must be installed for text extraction::

    pip install pymupdf
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Simple patterns to find member IDs like "B1", "C-01", "S2", "W3"
_MEMBER_PATTERN = re.compile(
    r"\b(?P<type>B|BEAM|COL|COLUMN|C|S|SLAB|W|WALL|F|FOOTING|ST|STAIR)"
    r"[-\s]?(?P<num>\d+)\b",
    re.IGNORECASE,
)

_DIMENSION_PATTERN = re.compile(
    r"(?P<dim>\d{2,4})\s*[xX×]\s*(?P<dim2>\d{2,4})"
)

_TYPE_MAP: dict[str, str] = {
    "b": "beam", "beam": "beam",
    "c": "column", "col": "column", "column": "column",
    "s": "slab", "slab": "slab",
    "w": "wall", "wall": "wall",
    "f": "footing", "footing": "footing",
    "st": "staircase", "stair": "staircase",
}


def _extract_text_blocks(file_path: str) -> list[str]:
    """
    Extract all text from a PDF using pymupdf (fitz).

    Parameters
    ----------
    file_path : str
        Absolute path to the PDF file.

    Returns
    -------
    list[str]
        One string per page of extracted text.
    """
    import fitz  # type: ignore[import]

    doc = fitz.open(file_path)
    pages = [page.get_text() for page in doc]
    doc.close()
    return pages


def parse_pdf(file_path: str) -> dict:
    """
    Parse a PDF structural drawing and return the Structural JSON schema.

    Since PDFs carry no machine-readable geometry, this function extracts
    member references from embedded text (e.g. schedules, annotations).
    Results are labelled as unverified and the engineer is prompted to confirm
    or supply a DXF file for higher accuracy.

    Parameters
    ----------
    file_path : str
        Absolute path to the ``.pdf`` file.

    Returns
    -------
    dict
        Structural JSON:
        ``{members, scale, raw_entity_count, parse_warnings, file_path, parsed_at}``
    """
    warnings: list[str] = []
    members: list[dict[str, Any]] = []

    try:
        pages = _extract_text_blocks(file_path)
    except ImportError:
        warnings.append(
            "pymupdf is not installed — PDF text extraction unavailable. "
            "Install with: pip install pymupdf  "
            "Alternatively, supply a DXF file for accurate geometry parsing."
        )
        return {
            "members": [],
            "scale": {"factor": 0.001, "unit": "mm", "detected": False},
            "raw_entity_count": 0,
            "parse_warnings": warnings,
            "file_path": file_path,
            "parsed_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        warnings.append(f"PDF read error: {exc}")
        return {
            "members": [],
            "scale": {"factor": 0.001, "unit": "mm", "detected": False},
            "raw_entity_count": 0,
            "parse_warnings": warnings,
            "file_path": file_path,
            "parsed_at": datetime.now(timezone.utc).isoformat(),
        }

    seen_ids: set[str] = set()

    for page_text in pages:
        for match in _MEMBER_PATTERN.finditer(page_text):
            type_key = match.group("type").lower()
            member_type = _TYPE_MAP.get(type_key, "unknown")
            if member_type == "unknown":
                continue

            raw_id = match.group(0).replace(" ", "").upper()
            if raw_id in seen_ids:
                continue
            seen_ids.add(raw_id)

            # Try to find a dimension near this match
            surrounding = page_text[max(0, match.start() - 60): match.end() + 60]
            dim_match = _DIMENSION_PATTERN.search(surrounding)

            b_mm = int(dim_match.group("dim")) if dim_match else 300
            h_mm = int(dim_match.group("dim2")) if dim_match else 500
            span_m = 5.0  # unknown from text; user must confirm

            members.append({
                "member_id": raw_id,
                "member_type": member_type,
                "meta": {
                    "source": "pdf_text_extraction",
                    "b_mm": b_mm,
                    "h_mm": h_mm,
                },
                "spans": [{"span_id": "S1", "length_m": span_m}],
                "spans_m": [span_m],
            })

    warnings.append(
        "PDF text extraction is approximate. Span lengths default to 5.0 m — "
        "please verify all member geometry in the Canvas before proceeding. "
        "Supplying a DXF file gives significantly higher accuracy."
    )

    logger.info(
        "PDF parse complete: %d page(s), %d member references detected.",
        len(pages),
        len(members),
    )

    return {
        "members": members,
        "scale": {"factor": 0.001, "unit": "mm", "detected": False},
        "raw_entity_count": len(members),
        "parse_warnings": warnings,
        "file_path": file_path,
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }

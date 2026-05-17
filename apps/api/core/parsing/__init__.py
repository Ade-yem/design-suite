"""
core/parsing/__init__.py
========================
DXF and PDF structural drawing parsers.

Entry points
------------
parse_file(file_path)  → Structural JSON dict  (dispatches by extension)
parse_dxf(file_path)   → Structural JSON dict
parse_pdf(file_path)   → Structural JSON dict  (text-only; geometry limited)
"""

from __future__ import annotations

from core.parsing.dxf_parser import extract_geometry
from core.parsing.pdf_parser import parse_pdf


def parse_file(file_path: str) -> dict:
    """
    Dispatch to the correct parser based on file extension.

    Parameters
    ----------
    file_path : str
        Absolute path to the uploaded DXF or PDF file.

    Returns
    -------
    dict
        Structural JSON schema:
        ``{members, scale, raw_entity_count, parse_warnings, file_path, parsed_at}``

    Raises
    ------
    ValueError
        If the file extension is not ``.dxf`` or ``.pdf``.
    """
    lower = file_path.lower()
    if lower.endswith(".dxf"):
        return extract_geometry(file_path)
    if lower.endswith(".pdf"):
        return parse_pdf(file_path)
    raise ValueError(
        f"Unsupported file type: '{file_path}'. "
        "Only .dxf and .pdf are accepted."
    )


__all__ = ["parse_file", "extract_geometry", "parse_pdf"]

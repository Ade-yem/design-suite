"""
PDF Export Engine
==================
Converts rendered HTML strings to PDF using WeasyPrint.

WeasyPrint was chosen because it:
* Consumes standard HTML + CSS — no proprietary format.
* Handles multi-page documents with CSS ``@page`` rules.
* Renders inline SVG natively (critical for BMD/SFD diagrams).
* Runs server-side in Python — no browser dependency.

All PDF output uses A4 portrait with engineering-standard margins defined
in the companion ``templates/base.html`` CSS.

Classes
-------
PDFExportEngine
    Converts an HTML string to PDF bytes.
    ``export(html, output_path=None)`` returns bytes or writes to file.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class PDFExportEngine:
    """
    PDF Export Engine.

    Wraps WeasyPrint's HTML-to-PDF pipeline. Accepts a fully rendered HTML
    string (produced by ``TemplateRenderer``) and returns the PDF as bytes
    or writes it to a file path.

    WeasyPrint is imported lazily — the design suite will run without it
    if only HTML preview mode is used.

    Parameters
    ----------
    None — stateless, reuse the same instance freely.

    Usage
    -----
    ::

        engine = PDFExportEngine()
        pdf_bytes = engine.export(html_string)

        # Or write directly to disk:
        engine.export(html_string, output_path=Path("/tmp/report.pdf"))
    """

    def export(
        self,
        html: str,
        output_path: Optional[Path] = None,
        base_url: Optional[str] = None,
    ) -> bytes:
        """
        Convert rendered HTML to a PDF document.

        Parameters
        ----------
        html : str
            Complete HTML document string as produced by ``TemplateRenderer``.
        output_path : Path, optional
            If provided, write the PDF bytes to this path and still return bytes.
        base_url : str, optional
            Base URL for resolving relative resources within the HTML
            (e.g. embedded fonts). Defaults to the templates directory.

        Returns
        -------
        bytes
            Raw PDF file content.

        Raises
        ------
        ImportError
            If WeasyPrint is not installed.
        RuntimeError
            If WeasyPrint fails to render the document.
        """
        try:
            from weasyprint import HTML, CSS
        except ImportError as exc:
            raise ImportError(
                "WeasyPrint is required for PDF export. "
                "Install it with: pip install weasyprint"
            ) from exc

        if base_url is None:
            base_url = str(Path(__file__).parent / "templates")

        logger.info("WeasyPrint: starting PDF conversion (%d chars HTML).", len(html))

        try:
            document = HTML(string=html, base_url=base_url)
            pdf_bytes: bytes = document.write_pdf()
        except Exception as exc:
            raise RuntimeError(
                f"WeasyPrint failed to render the PDF document: {exc}"
            ) from exc

        logger.info("WeasyPrint: PDF generated (%d bytes).", len(pdf_bytes))

        if output_path is not None:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(pdf_bytes)
            logger.info("PDF written to: %s", output_path)

        return pdf_bytes

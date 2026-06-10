"""
Script to rasterize a sample PDF floor beam plan and output the individual pages as PNGs.
"""

from __future__ import annotations

import os
import sys

# Ensure backend directory is in python path so imports resolve correctly when run directly
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

import logging
from typing import Final, List

import pdf_normalizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_PDF_NAME: Final[str] = "Floor-beam.pdf"


def find_pdf_path(filename: str) -> str | None:
    """
    Search for the PDF file in standard relative directories.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    search_paths: List[str] = [
        os.path.join(script_dir, filename),
        os.path.join(os.path.dirname(script_dir), "uploads", filename),
        os.path.join(".", filename),
    ]
    for path in search_paths:
        if os.path.exists(path):
            return path
    return None


def main() -> None:
    """
    Load a sample PDF, rasterize it into PNG images, and save them to the current directory.
    """
    pdf_path = find_pdf_path(DEFAULT_PDF_NAME)
    if not pdf_path:
        logger.error("Sample PDF '%s' not found in search paths.", DEFAULT_PDF_NAME)
        sys.exit(1)

    try:
        logger.info("Rasterizing PDF file: %s", pdf_path)
        images = pdf_normalizer.rasterize_pdf(pdf_path)

        if not images:
            logger.warning("No images were generated from the PDF.")
            return

        for i, image in enumerate(images):
            output_name = f"output{i}.png"
            with open(output_name, "wb") as f:
                f.write(image.png)
            logger.info("Saved image %d to %s (%dx%d px)", i, output_name, image.width, image.height)

    except Exception as err:
        logger.exception("An error occurred while rasterizing the PDF: %s", err)
        sys.exit(1)


if __name__ == "__main__":
    main()


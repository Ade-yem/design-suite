"""
Script to extract slab geometries deterministically from parsed beam members.
"""

from __future__ import annotations

import json
import os
import sys

# Ensure backend directory is in python path so imports resolve correctly when run directly
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

import logging
from typing import Final

from parser_pipeline import extract_slabs_deterministically

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GEOMETRY_FILE: Final[str] = "parsed_geometry.json"


def main() -> None:
    """
    Load parsed beam member geometry, extract slabs deterministically, and save the updated geometry.
    """
    if not os.path.exists(GEOMETRY_FILE):
        logger.error("Parsed geometry file not found at: %s", os.path.abspath(GEOMETRY_FILE))
        sys.exit(1)

    try:
        logger.info("Reading geometry file: %s", GEOMETRY_FILE)
        with open(GEOMETRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        beam_members = data.get("members", [])
        logger.info("Found %d beam members in the data", len(beam_members))

        slab_members = extract_slabs_deterministically(beam_members)
        logger.info("Extracted %d slabs deterministically", len(slab_members))

        data["slabs"] = slab_members

        with open(GEOMETRY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("Successfully saved updated geometry to %s", GEOMETRY_FILE)

    except json.JSONDecodeError as err:
        logger.error("Failed to parse JSON from %s: %s", GEOMETRY_FILE, err)
        sys.exit(1)
    except Exception as err:
        logger.exception("An unexpected error occurred: %s", err)
        sys.exit(1)


if __name__ == "__main__":
    main()

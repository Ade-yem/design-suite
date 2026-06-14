"""
Module for testing DXF file parsing using ezdxf.
This script extracts and prints basic geometric entities from a DXF file.
"""

import sys
import os
import json
import asyncio
# Add the apps/api directory to sys.path to allow importing the 'core' module
# This ensures that 'core' is found regardless of where the script is run from.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.parsing.dxf_parser import extract_geometry
from core.parsing.extractor import _run_member_extraction
def parse_dxf_entities(file_path: str):
    """
    Parses the given DXF file, prints details about its entities,
    and dumps the resulting extraction geometry to a 'result.json' file.

    Args:
        file_path (str): The absolute or relative path to the DXF file.

    Returns:
        None
    """
    print(f"Target file: {file_path}")

    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return

    try:
        result = extract_geometry(file_path)
        members = asyncio.run(_run_member_extraction("project_id", result))
        output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "result.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(members, f, indent=2)
        print(f"Successfully dumped result to: {output_path}")
    except Exception as e:
        print(f"An error occurred during parsing: {e}")

if __name__ == "__main__":
    # Determine the project root to find the sample file correctly
    # Current script is in apps/api/script/test_dxf.py
    # Project root is three levels up
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
    target_file = os.path.join(project_root, "sample", "Floor-beam.dxf")

    parse_dxf_entities(target_file)

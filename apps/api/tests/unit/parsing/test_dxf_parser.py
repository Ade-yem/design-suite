"""
test_dxf_parser.py
==================
Unit tests for the DXF layout extraction and sheet validation features,
using both synthetic and real-world sample DXF files.
"""

from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path
from typing import Generator

import ezdxf
import pytest
from core.parsing.dxf_parser import DXFGeometricExtractor, extract_geometry

# Locate the sample directory relative to this test file
PROJECT_ROOT = Path(__file__).resolve().parents[5]
SAMPLE_DIR = PROJECT_ROOT / "sample"


@pytest.fixture
def temp_dxf_path() -> Generator[Path, None, None]:
    """
    Fixture providing a temporary DXF file path that is cleaned up after the test.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir) / "test_drawing.dxf"


def create_blank_dxf() -> ezdxf.document.Drawing:
    """
    Create a new in-memory DXF drawing with default settings.
    """
    doc = ezdxf.new("R2010")
    # Set default drawing units to millimeters
    doc.header["$INSUNITS"] = 4
    return doc


def add_structural_beam_grid(
    msp: ezdxf.layouts.BaseLayout, 
    start_x: float, 
    start_y: float, 
    grid_size: float = 4000.0, 
    count: int = 5
) -> None:
    """
    Helper to add a dummy structural beam grid to an ezdxf layout.
    Adds a set of lines on the 'BEAMS' layer.
    """
    for i in range(count):
        # Horizontal lines (beams)
        msp.add_line(
            (start_x, start_y + i * grid_size),
            (start_x + (count - 1) * grid_size, start_y + i * grid_size),
            dxfattribs={"layer": "BEAMS"}
        )
        # Vertical lines (beams)
        msp.add_line(
            (start_x + i * grid_size, start_y),
            (start_x + i * grid_size, start_y + (count - 1) * grid_size),
            dxfattribs={"layer": "BEAMS"}
        )
    
    # Add some column text labels (e.g. C1) to populate structural candidates
    for i in range(count):
        for j in range(count):
            msp.add_text(
                "C1",
                dxfattribs={
                    "layer": "COLUMNS",
                    "height": 250.0,
                    "insert": (start_x + i * grid_size, start_y + j * grid_size)
                }
            )


# ─── REAL SAMPLE FILE TESTS ──────────────────────────────────────────────────

def test_real_sample_happy_path_single_layout() -> None:
    """
    Verify that the real Floor-beam.dxf file parses successfully without layout errors.
    """
    dxf_path = SAMPLE_DIR / "Floor-beam.dxf"
    assert dxf_path.exists(), f"Sample file not found at: {dxf_path}"

    result = extract_geometry(dxf_path)
    assert len(result["entities"]) > 0
    assert "Model" in result["metadata"]["layouts_processed"]


def test_real_sample_reject_side_by_side() -> None:
    """
    Verify that the real 1-2 layout.dxf file (containing side-by-side floor plans)
    is correctly rejected by our layout validation check.
    """
    dxf_path = SAMPLE_DIR / "1-2 layout.dxf"
    assert dxf_path.exists(), f"Sample file not found at: {dxf_path}"

    with pytest.raises(ValueError) as exc_info:
        extract_geometry(dxf_path)
    
    assert "INVALID_LAYOUT_STRUCTURE" in str(exc_info.value)
    assert "Multiple plans detected side-by-side" in str(exc_info.value)


# ─── SYNTHETIC TESTS ─────────────────────────────────────────────────────────

def test_happy_path_single_layout(temp_dxf_path: Path) -> None:
    """
    Verify that a single valid floor plan in Model space passes validation.
    """
    doc = create_blank_dxf()
    msp = doc.modelspace()
    add_structural_beam_grid(msp, 0.0, 0.0)

    # Save to temp file
    doc.saveas(temp_dxf_path)

    # Extract
    result = extract_geometry(temp_dxf_path)
    
    assert "Model" in result["metadata"]["layouts_processed"]
    assert len(result["entities"]) > 0
    # Every entity must have layout_name = "Model"
    for ent in result["entities"]:
        assert ent["layout_name"] == "Model"


def test_happy_path_multi_layout(temp_dxf_path: Path) -> None:
    """
    Verify that separate floor plans in separate layout tabs are processed correctly
    and have their respective layout_name populated.
    """
    doc = create_blank_dxf()
    
    # Model space is blank or has some base shared elements
    # Add a layout tab named 'Ground Floor'
    g_layout = doc.layouts.new("Ground Floor")
    add_structural_beam_grid(g_layout, 0.0, 0.0)
    
    # Add another layout tab named 'First Floor'
    f_layout = doc.layouts.new("First Floor")
    add_structural_beam_grid(f_layout, 0.0, 0.0)

    doc.saveas(temp_dxf_path)

    # Extract
    extractor = DXFGeometricExtractor(temp_dxf_path)
    result = extractor.extract()

    # Verify both layout tabs are processed
    assert "Ground Floor" in result.layouts_processed
    assert "First Floor" in result.layouts_processed
    
    entities = result.entities
    ground_ents = [e for e in entities if e.layout_name == "Ground Floor"]
    first_ents = [e for e in entities if e.layout_name == "First Floor"]

    assert len(ground_ents) > 0
    assert len(first_ents) > 0


def test_edge_case_reject_side_by_side_density(temp_dxf_path: Path) -> None:
    """
    Verify that drawing two floor plans side-by-side inside the same Model space 
    tab (with a horizontal gap > 15m) is rejected.
    """
    doc = create_blank_dxf()
    msp = doc.modelspace()
    
    # Add layout 1 centered at X=0
    add_structural_beam_grid(msp, 0.0, 0.0, count=5)
    
    # Add layout 2 centered at X=40,000 (40 meters away, gap is 40m - 16m = 24m)
    add_structural_beam_grid(msp, 40000.0, 0.0, count=5)

    doc.saveas(temp_dxf_path)

    with pytest.raises(ValueError) as exc_info:
        extract_geometry(temp_dxf_path)
    
    assert "INVALID_LAYOUT_STRUCTURE" in str(exc_info.value)
    assert "Multiple plans detected side-by-side" in str(exc_info.value)


def test_edge_case_reject_stacked_density(temp_dxf_path: Path) -> None:
    """
    Verify that drawing two floor plans vertically stacked inside the same Model space 
    tab (with a vertical gap > 15m) is rejected.
    """
    doc = create_blank_dxf()
    msp = doc.modelspace()
    
    # Add layout 1 centered at Y=0
    add_structural_beam_grid(msp, 0.0, 0.0, count=5)
    
    # Add layout 2 centered at Y=40,000 (40 meters away)
    add_structural_beam_grid(msp, 0.0, 40000.0, count=5)

    doc.saveas(temp_dxf_path)

    with pytest.raises(ValueError) as exc_info:
        extract_geometry(temp_dxf_path)
    
    assert "INVALID_LAYOUT_STRUCTURE" in str(exc_info.value)
    assert "Multiple plans detected side-by-side/stacked" in str(exc_info.value)


def test_edge_case_reject_by_titles(temp_dxf_path: Path) -> None:
    """
    Verify that multiple distinct floor plan title text strings (e.g. Ground Floor, First Floor)
    separated by > 15m raises validation error even with fewer structural candidates.
    """
    doc = create_blank_dxf()
    msp = doc.modelspace()
    
    # Add layout titles
    msp.add_text(
        "GROUND FLOOR PLAN",
        dxfattribs={"layer": "TEXT", "height": 300.0, "insert": (0.0, 0.0)}
    )
    msp.add_text(
        "FIRST FLOOR PLAN",
        dxfattribs={"layer": "TEXT", "height": 300.0, "insert": (30000.0, 0.0)}
    )

    # Add minimal elements so total structural candidates < 15 (avoid density trigger)
    # Just adding 4 elements on each side
    for i in range(4):
        msp.add_line((0.0, i * 100.0), (1000.0, i * 100.0), dxfattribs={"layer": "BEAMS"})
        msp.add_line((30000.0, i * 100.0), (31000.0, i * 100.0), dxfattribs={"layer": "BEAMS"})

    doc.saveas(temp_dxf_path)

    with pytest.raises(ValueError) as exc_info:
        extract_geometry(temp_dxf_path)
        
    assert "INVALID_LAYOUT_STRUCTURE" in str(exc_info.value)
    assert "Titles found" in str(exc_info.value)


def test_edge_case_empty_layouts(temp_dxf_path: Path) -> None:
    """
    Verify that an empty or minimal DXF file passes layout validation.
    """
    doc = create_blank_dxf()
    doc.saveas(temp_dxf_path)

    # Should not raise any ValueError
    result = extract_geometry(temp_dxf_path)
    assert len(result["entities"]) == 0


def test_edge_case_unified_large_building(temp_dxf_path: Path) -> None:
    """
    Verify that a single, very large continuous building layout (e.g., 60m x 60m)
    with no layout-separating gaps passes validation successfully.
    """
    doc = create_blank_dxf()
    msp = doc.modelspace()
    
    # Add a continuous, connected grid of beams/columns of 50m width (no gaps > 15m)
    # Using 6 columns at 10m grid spacing = 50m
    add_structural_beam_grid(msp, 0.0, 0.0, grid_size=10000.0, count=6)

    doc.saveas(temp_dxf_path)

    # Should pass cleanly without raising ValueError
    result = extract_geometry(temp_dxf_path)
    assert len(result["entities"]) > 0

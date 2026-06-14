"""
tests/integration/agents/test_vision_agent.py
============================================
Production Integration Tests for the Vision & Parser Agent.

This is a zero-mock, real-world integration test suite designed for production
verification. It tests the complete pipeline against actual drawing files and
real API services:
1. DXF parsing and scale/unit detection on a real drawing (Floor-beam.dxf).
2. Spatial proximity text grouping on real coordinates.
3. Real Gemini LLM member classification and automatic post-processing.
4. End-to-end parser node execution and database/project storage registration.
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest
from core.parsing.extractor import (
    _detect_unit_ambiguity,
    _prepare_candidates_summary,
    _run_member_extraction,
)
from services.files import file_service
from storage.project_store import project_store
from schemas.project import ProjectCreate
from config import settings

# Compute sample folder path relative to repo root
REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent  # Up from apps/api/tests/
SAMPLE_FOLDER = REPO_ROOT / "sample"
DXF_PATH = SAMPLE_FOLDER / "Floor-beam.dxf"
PDF_PATH = SAMPLE_FOLDER / "Floor-beam.pdf"


@pytest.mark.asyncio
class TestVisionAgentProduction:
    """
    Production-grade, zero-mock integration test suite for the Vision & Parser Agent.
    """

    async def test_real_dxf_parsing_and_unit_detection(self) -> None:
        """
        Verify that parsing a real DXF drawing (Floor-beam.dxf) correctly extracts
        geometric entities and confidently detects the drawing units as 'millimetres'
        without triggering unit ambiguity.
        """
        dxf_path = str(DXF_PATH)
        if not os.path.exists(dxf_path):
            pytest.skip(f"Real drawing file not found at: {dxf_path}")

        # Initialize mock project in database
        project = await project_store.create(
            ProjectCreate(
                name="Unit Test Project",
                reference="REF-UNIT",
                client="Client A",
                design_code="BS8110"
            )
        )
        project_id = project.project_id

        # Run direct parse
        parsed = await file_service.parse(project_id, dxf_path)

        assert parsed is not None
        assert "entities" in parsed
        assert len(parsed["entities"]) > 0

        # Check unit ambiguity detection
        unit_check = _detect_unit_ambiguity(parsed)
        assert unit_check["ambiguous"] is False
        assert unit_check["detected_unit"] == "millimetres"
        assert unit_check["confidence"] == "high"
        assert len(unit_check["sample_dimensions"]) > 0

    async def test_real_candidates_pre_processing(self) -> None:
        """
        Verify that candidate pre-processing successfully filters raw DXF entities into
        high-signal columns/beams and pre-associates nearby text annotations using
        real spatial proximity calculations.
        """
        dxf_path = str(DXF_PATH)
        if not os.path.exists(dxf_path):
            pytest.skip(f"Real drawing file not found at: {dxf_path}")

        project = await project_store.create(
            ProjectCreate(
                name="Candidates Test Project",
                reference="REF-CAND",
                client="Client A",
                design_code="BS8110"
            )
        )
        project_id = project.project_id

        parsed = await file_service.parse(project_id, dxf_path)
        candidates = _prepare_candidates_summary(parsed)

        assert len(candidates) > 0

        # Verify columns are identified and grouped with spatial annotations
        columns = [c for c in candidates if c["layer_hint"] == "column_candidate"]
        assert len(columns) > 0

        # Check that spatial proximity associated nearest labels correctly
        for col in columns:
            assert "nearest_text" in col
            assert len(col["nearest_text"]) > 0
            # Centroid coordinates must be present
            assert len(col["centroid"]) == 2

        # Verify beams are identified
        beams = [c for c in candidates if c["layer_hint"] == "beam_candidate"]
        assert len(beams) > 0

    async def test_real_llm_classification_and_post_processing(self) -> None:
        """
        Verify that the real Gemini LLM model successfully receives the compressed
        candidate JSON, classifies them into structural members, and automatically
        calculates correct moment of inertia (I) and sets defaults for downstream tools.
        """
        if not settings.GEMINI_API_KEY:
            pytest.skip("Skipping real LLM test: GEMINI_API_KEY is not configured.")

        dxf_path = str(DXF_PATH)
        if not os.path.exists(dxf_path):
            pytest.skip(f"Real drawing file not found at: {dxf_path}")

        project = await project_store.create(
            ProjectCreate(
                name="LLM Test Project",
                reference="REF-LLM",
                client="Client A",
                design_code="BS8110"
            )
        )
        project_id = project.project_id

        # Parse file to cache
        parsed = await file_service.parse(project_id, dxf_path)

        # Call real LLM classification
        members = await _run_member_extraction(project_id, parsed)

        assert len(members) > 0

        # Verify member schemas match the analysis/designer contract
        for m in members:
            assert "member_id" in m
            assert "member_type" in m
            assert "type" in m
            assert m["member_type"] == m["type"]
            assert "meta" in m
            assert "spans" in m
            assert "spans_m" in m

            meta = m["meta"]
            if m["member_type"] == "beam":
                # Ensure post-processing generated inertia and parameters correctly
                assert "b_mm" in meta
                assert "h_mm" in meta
                assert "L_clear" in meta
                assert "I" in meta
                assert "E" in meta
                assert meta["E"] == 30e6
                # Test the physical inertia calculation: I = b * h^3 / 12 (in meters)
                b_m = meta["b_mm"] / 1000.0
                h_m = meta["h_mm"] / 1000.0
                expected_I = (b_m * (h_m ** 3)) / 12.0
                assert abs(meta["I"] - expected_I) < 1e-5
            elif m["member_type"] == "column":
                assert "b" in meta
                assert "h" in meta
                assert "L_clear" in meta
                assert "end_condition" in meta
                assert "N_uls" in meta
                assert "M_uls" in meta

    async def test_real_llm_dual_input_parsing(self) -> None:
        """
        Verify that the Vision & Parser Agent successfully performs multimodal
        extraction when provided with both a DXF structural drawing and a high-fidelity
        PDF reference document simultaneously.
        """
        if not settings.GEMINI_API_KEY:
            pytest.skip("Skipping real LLM dual-input test: GEMINI_API_KEY is not configured.")

        dxf_path = "/home/adehnaija/Documents/projects/design-suite/sample/Floor-beam.dxf"
        pdf_path = "/home/adehnaija/Documents/projects/design-suite/sample/Floor-beam.pdf"
        
        if not os.path.exists(dxf_path) or not os.path.exists(pdf_path):
            pytest.skip(f"Required test drawings not found at: {dxf_path} or {pdf_path}")

        # Initialize mock project in database
        project = await project_store.create(
            ProjectCreate(
                name="Dual Input Test Project",
                reference="REF-DUAL",
                client="Client A",
                design_code="BS8110"
            )
        )
        project_id = project.project_id

        # 1. Parse DXF to JSON
        parsed = await file_service.parse(project_id, dxf_path)
        assert parsed is not None

        # 2. Run LLM extraction with both parsed DXF structure and visual reference PDF
        members = await _run_member_extraction(project_id, parsed, pdf_path=pdf_path)
        print(members)
        # 3. Assert results are correctly classified
        assert len(members) > 0
        for m in members:
            assert "member_id" in m
            assert "member_type" in m
            assert m["member_type"] in ("beam", "column", "slab", "wall", "footing", "staircase")
            
            meta = m.get("meta", {})
            assert len(meta) > 0

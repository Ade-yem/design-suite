import asyncio
import os

from agents.parser import _run_member_extraction
from config import settings
from schemas.project import ProjectCreate
from services.files import file_service
from storage.project_store import project_store
from dotenv import load_dotenv

load_dotenv()
async def test_real_llm_dual_input_parsing() -> None:
    """
    Verify that the Vision & Parser Agent successfully performs multimodal
    extraction when provided with both a DXF structural drawing and a high-fidelity
    PDF reference document simultaneously.
    """
    if not settings.GEMINI_API_KEY:
        raise ValueError("No api key found")

    dxf_path = "/home/adehnaija/Documents/projects/design-suite/sample/Floor-beam.dxf"
    pdf_path = "/home/adehnaija/Documents/projects/design-suite/sample/Floor-beam.pdf"
    
    if not os.path.exists(dxf_path) or not os.path.exists(pdf_path):
        raise ValueError(f"Required test drawings not found at: {dxf_path} or {pdf_path}")

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

if __name__ == "__main__":
    asyncio.run(test_real_llm_dual_input_parsing())

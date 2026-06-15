"""
tests/unit/parsing/test_storey_generator.py
===========================================
Unit tests for storey extrapolation and column stack linkage.
"""

from __future__ import annotations

from typing import Any
import pytest
from core.parsing.storey_generator import extrapolate_storeys, link_column_stacks
from services.loading import loading_service
from storage.project_store import project_store
from storage.stage_result_store import stage_result_store
from agents.graph import app as graph_app


def test_extrapolate_single_storey():
    typical_members = [
        {"member_id": "C1", "member_type": "column", "layout_name": "Model", "center_point": {"x": 0, "y": 0}},
        {"member_id": "B1", "member_type": "beam", "layout_name": "Model", "start_point": {"x": 0, "y": 0}, "end_point": {"x": 5000, "y": 0}},
    ]
    
    result = extrapolate_storeys(
        typical_members=typical_members,
        num_storeys=1,
        storey_height_m=3.0,
        layouts_processed=["Model"],
    )
    
    assert len(result) == 2
    assert result[0]["member_id"] == "C1"
    assert result[0]["storey"] == "L01"
    assert result[0]["elevation_m"] == 0.0
    
    assert result[1]["member_id"] == "B1"
    assert result[1]["storey"] == "L01"
    assert result[1]["elevation_m"] == 0.0


def test_extrapolate_multi_storey_typical():
    typical_members = [
        {"member_id": "C1", "member_type": "column", "layout_name": "Model", "center_point": {"x": 0, "y": 0}},
        {"member_id": "B1", "member_type": "beam", "layout_name": "Model", "start_point": {"x": 0, "y": 0}, "end_point": {"x": 5000, "y": 0}},
    ]
    
    result = extrapolate_storeys(
        typical_members=typical_members,
        num_storeys=3,
        storey_height_m=3.0,
        layouts_processed=["Model"],
    )
    
    # 2 members * 3 storeys = 6 members
    assert len(result) == 6
    
    # Check storey 1
    assert result[0]["member_id"] == "L01-C1"
    assert result[0]["storey"] == "L01"
    assert result[0]["elevation_m"] == 0.0
    
    # Check storey 2
    assert result[2]["member_id"] == "L02-C1"
    assert result[2]["storey"] == "L02"
    assert result[2]["elevation_m"] == 3.0
    
    # Check storey 3
    assert result[4]["member_id"] == "L03-C1"
    assert result[4]["storey"] == "L03"
    assert result[4]["elevation_m"] == 6.0


def test_extrapolate_multi_sheet_mapping():
    typical_members = [
        # Ground Floor layout
        {"member_id": "C1", "member_type": "column", "layout_name": "Ground Floor", "center_point": {"x": 0, "y": 0}},
        # First Floor layout
        {"member_id": "C2", "member_type": "column", "layout_name": "First Floor", "center_point": {"x": 0, "y": 0}},
    ]
    
    result = extrapolate_storeys(
        typical_members=typical_members,
        num_storeys=3,
        storey_height_m=3.5,
        layouts_processed=["Ground Floor", "First Floor"],
    )
    
    # 3 storeys.
    # L01 -> Ground Floor (contains C1) -> L01-C1
    # L02 -> First Floor (contains C2) -> L02-C2
    # L03 -> First Floor duplicated (contains C2) -> L03-C2
    assert len(result) == 3
    
    assert result[0]["member_id"] == "L01-C1"
    assert result[0]["storey"] == "L01"
    assert result[0]["elevation_m"] == 0.0
    
    assert result[1]["member_id"] == "L02-C2"
    assert result[1]["storey"] == "L02"
    assert result[1]["elevation_m"] == 3.5
    
    assert result[2]["member_id"] == "L03-C2"
    assert result[2]["storey"] == "L03"
    assert result[2]["elevation_m"] == 7.0


def test_column_stack_linkage():
    typical_members = [
        {"member_id": "C1", "member_type": "column", "layout_name": "Model", "center_point": {"x": 100.0, "y": 200.0}},
        # Column that is offset by 150mm (within 300mm limit)
        {"member_id": "C2", "member_type": "column", "layout_name": "Model", "center_point": {"x": 100.0, "y": 350.0}},
        # Column that is offset by 400mm (exceeds 300mm limit)
        {"member_id": "C3", "member_type": "column", "layout_name": "Model", "center_point": {"x": 500.0, "y": 200.0}},
    ]
    
    result = extrapolate_storeys(
        typical_members=typical_members,
        num_storeys=2,
        storey_height_m=3.0,
        layouts_processed=["Model"],
    )
    
    # We should have 6 columns: L01-C1, L01-C2, L01-C3 and L02-C1, L02-C2, L02-C3
    # L01-C1 (100, 200) -> L02-C1 (100, 200): dist = 0 -> Link!
    # L01-C2 (100, 350) -> L02-C2 (100, 350): dist = 0 -> Link!
    # L01-C3 (500, 200) -> L02-C3 (500, 200): dist = 0 -> Link!
    
    # Let's verify standard links
    m_by_id = {m["member_id"]: m for m in result}
    
    assert m_by_id["L01-C1"]["meta"]["child_column_id"] == "L02-C1"
    assert m_by_id["L02-C1"]["meta"]["parent_column_id"] == "L01-C1"
    
    assert m_by_id["L01-C2"]["meta"]["child_column_id"] == "L02-C2"
    assert m_by_id["L02-C2"]["meta"]["parent_column_id"] == "L01-C2"


def test_column_stack_linkage_distance_tolerance():
    # Columns L01-C1 and L02-C1 offset, testing distance bounds
    col_l01: dict[str, Any] = {"member_id": "L01-C1", "member_type": "column", "storey": "L01", "center_point": {"x": 0.0, "y": 0.0}}
    
    # 1. Dist <= 300mm
    col_l02_close: dict[str, Any] = {"member_id": "L02-C1", "member_type": "column", "storey": "L02", "center_point": {"x": 200.0, "y": 200.0}} # dist = sqrt(80000) ~ 282.8mm
    members = [col_l01, col_l02_close]
    link_column_stacks(members, tolerance_mm=300.0)
    assert col_l01["meta"]["child_column_id"] == "L02-C1"
    assert col_l02_close["meta"]["parent_column_id"] == "L01-C1"
    
    # 2. Dist > 300mm
    col_l01_2: dict[str, Any] = {"member_id": "L01-C1", "member_type": "column", "storey": "L01", "center_point": {"x": 0.0, "y": 0.0}}
    col_l02_far: dict[str, Any] = {"member_id": "L02-C1", "member_type": "column", "storey": "L02", "center_point": {"x": 250.0, "y": 250.0}} # dist = sqrt(125000) ~ 353.5mm
    members_far = [col_l01_2, col_l02_far]
    link_column_stacks(members_far, tolerance_mm=300.0)
    assert "meta" not in col_l01_2 or "child_column_id" not in col_l01_2.get("meta", {})
    assert "meta" not in col_l02_far or "parent_column_id" not in col_l02_far.get("meta", {})


@pytest.mark.asyncio
async def test_loading_service_integration():
    from schemas.project import ProjectCreate
    
    proj_data = ProjectCreate(
        name="Storey Test",
        reference="REF-001",
        client="Client",
        design_code="BS8110"
    )
    
    # Initialize mock project
    project = await project_store.create(
        data=proj_data,
        organisation_id="org-1"
    )
    project_id = project.project_id
    
    from services.files import file_service
    
    # Setup typical 2D geometry in stage_result_store via file_service
    mock_geometry = {
        "layouts_processed": ["Model"],
        "members": [
            {"member_id": "C1", "member_type": "column", "layout_name": "Model", "center_point": {"x": 0, "y": 0}},
            {"member_id": "B1", "member_type": "beam", "layout_name": "Model", "start_point": {"x": 0, "y": 0}, "end_point": {"x": 5000, "y": 0}},
        ]
    }
    await file_service.register_geometry(project_id, mock_geometry)
    
    # Inject project_parameters with num_storeys=3 into LangGraph app state
    config = {"configurable": {"thread_id": project_id}}
    await graph_app.aupdate_state(
        config,
        {
            "project_parameters": {
                "num_storeys": 3,
                "storey_height_m": 3.0
            }
        }
    )
    
    # Define simple load parameters
    load_def = {
        "design_code": "BS8110",
        "occupancy_category": "office",
        "dead_loads": {
            "finishes_kNm2": 1.5,
            "screed_kNm2": 0.8,
            "services_kNm2": 0.5,
            "partitions_kNm2": 1.0,
            "cladding_kNm": 0.0
        },
        "imposed_loads": {
            "floor_qk_kNm2": 2.5,
            "roof_qk_kNm2": 0.6,
            "stair_qk_kNm2": 3.0
        },
        "member_overrides": []
    }
    await loading_service.define(project_id, load_def)
    
    # Run combinations (this should trigger storey generator internally!)
    output = await loading_service.run_combinations(project_id)
    
    assert output is not None
    assert output["design_code"] == "BS8110"
    
    # Verify that the members in the output are extrapolated across 3 storeys!
    m_ids = [m["member_id"] for m in output["members"]]
    assert len(m_ids) == 6
    assert f"L01-C1" in m_ids
    assert f"L02-C1" in m_ids
    assert f"L03-C1" in m_ids
    assert f"L01-B1" in m_ids
    assert f"L02-B1" in m_ids
    assert f"L03-B1" in m_ids
    
    # Verify database project members registry was updated
    registered_mids = await project_store.get_member_ids(project_id)
    assert set(registered_mids) == {f"L01-C1", f"L02-C1", f"L03-C1", f"L01-B1", f"L02-B1", f"L03-B1"}

import os
os.environ["PROJECT_STORE_BACKEND"] = "memory"

import pytest
from httpx import ASGITransport, AsyncClient
from main import app
from storage.project_store import project_store
from schemas.project import ProjectCreate, ProjectStatus


@pytest.fixture(autouse=True)
async def clear_stores():
    """Ensure a clean slate for every test."""
    if hasattr(project_store, "_projects"):
        project_store._projects.clear()
    if hasattr(project_store, "_members"):
        project_store._members.clear()

@pytest.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

@pytest.fixture
async def test_project():
    data = ProjectCreate(
        name="Test Project",
        reference="REF-123",
        client="Test Client",
        design_code="BS8110"
    )
    project = await project_store.create(data)
    return project.model_dump()

@pytest.fixture
async def geometry_verified_project():
    """Project already past Gate 1 — GEOMETRY_VERIFIED status."""
    data = ProjectCreate(
        name="Test Project",
        reference="REF-123",
        client="Test Client",
        design_code="BS8110"
    )
    project = await project_store.create(data)
    await project_store.advance_status(project.project_id, ProjectStatus.GEOMETRY_VERIFIED)
    resolved = await project_store.get(project.project_id)
    assert resolved is not None
    return resolved.model_dump()

@pytest.fixture
async def project_with_loads_defined(async_client, test_project):
    # Stub fixture for integration testing
    return await test_project

@pytest.fixture
async def project_with_analysis_complete(async_client, test_project):
    # Stub fixture
    return await test_project

@pytest.fixture
async def project_with_design_failures(async_client, test_project):
    # Stub fixture
    proj = await test_project
    return {"project_id": proj["project_id"], "failed_member_id": "B-01"}

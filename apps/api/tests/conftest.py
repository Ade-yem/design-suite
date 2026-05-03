import pytest
from httpx import ASGITransport, AsyncClient
from main import app
from storage.project_store import project_store
from schemas.project import ProjectCreate

@pytest.fixture(autouse=True)
def clear_stores():
    """Ensure a clean slate for every test."""
    project_store._projects.clear()
    project_store._members.clear()

@pytest.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

@pytest.fixture
def test_project():
    data = ProjectCreate(
        name="Test Project",
        reference="REF-123",
        client="Test Client",
        design_code="BS8110"
    )
    project = project_store.create(data)
    return project.model_dump()

@pytest.fixture
async def project_with_loads_defined(async_client, test_project):
    # Stub fixture for integration testing
    return test_project

@pytest.fixture
async def project_with_analysis_complete(async_client, test_project):
    # Stub fixture
    return test_project

@pytest.fixture
async def project_with_design_failures(async_client, test_project):
    # Stub fixture
    return {"project_id": test_project["project_id"], "failed_member_id": "B-01"}

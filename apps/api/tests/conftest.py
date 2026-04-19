import pytest
from httpx import AsyncClient
from main import app

@pytest.fixture
async def async_client():
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

@pytest.fixture
def test_project():
    return {"project_id": "test_proj_123", "design_code": "BS8110"}

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

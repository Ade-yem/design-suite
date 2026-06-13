import os
os.environ["PROJECT_STORE_BACKEND"] = "memory"
os.environ["GEMINI_API_KEY"] = "dummy-key-for-testing"
os.environ["GOOGLE_API_KEY"] = "dummy-key-for-testing"

import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage
from main import app
from storage.project_store import project_store
from storage.artifact_store import artifact_store
from schemas.project import ProjectCreate, ProjectStatus


@pytest.fixture(autouse=True)
async def clear_stores():
    """Ensure a clean slate for every test."""
    if hasattr(project_store, "_projects"):
        project_store._projects.clear()
    if hasattr(project_store, "_members"):
        project_store._members.clear()
    if hasattr(artifact_store, "clear"):
        artifact_store.clear()

    from services.files import file_service
    from storage.job_store import job_store

    if hasattr(file_service, "_store"):
        file_service._store._parsed.clear()
        file_service._store._scale.clear()

    await job_store.clear()


@pytest.fixture(autouse=True)
def mock_llm_calls(monkeypatch):
    """Mock all LLM calls to return canned responses without hitting the API."""
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(
        return_value=AIMessage(content='{"key": "value"}')
    )
    mock_llm.invoke = MagicMock(
        return_value=AIMessage(content='{"key": "value"}')
    )

    def mock_get_llm():
        return mock_llm

    # agents.parser does not use LLM, hence doesn't define _get_llm
    # monkeypatch.setattr("agents.parser._get_llm", mock_get_llm)
    monkeypatch.setattr("agents.analyst._get_llm", mock_get_llm)
    monkeypatch.setattr("agents.designer._get_llm", mock_get_llm)

@pytest.fixture
async def authenticated_user():
    """Create a test user for authenticated API tests."""
    from db.models.user import User
    import uuid

    user = User(
        id=uuid.uuid4(),
        email="testuser@example.com",
        is_active=True,
        is_verified=True,
        is_superuser=False,
        hashed_password="hashed_dummy_password",
        full_name="Test User",
        role="engineer",
        organisation_id="test-org-id",
    )
    return user


@pytest.fixture
async def async_client():
    """Async client for API tests (unauthenticated by default)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
async def authenticated_client(async_client, authenticated_user):
    """
    Async client with mocked authentication for API tests that need auth.
    """
    from auth.dependencies import current_active_user

    app.dependency_overrides[current_active_user] = lambda: authenticated_user

    yield async_client

    # Cleanup: remove override
    app.dependency_overrides.clear()


@pytest.fixture
async def test_project(authenticated_user):
    data = ProjectCreate(
        name="Test Project",
        reference="REF-123",
        client="Test Client",
        design_code="BS8110"
    )
    project = await project_store.create(data, organisation_id=authenticated_user.organisation_id)
    return project.model_dump()


@pytest.fixture
async def geometry_verified_project(authenticated_user):
    """Project already past Gate 1 — GEOMETRY_VERIFIED status."""
    data = ProjectCreate(
        name="Test Project",
        reference="REF-123",
        client="Test Client",
        design_code="BS8110"
    )
    project = await project_store.create(data, organisation_id=authenticated_user.organisation_id)
    await project_store.advance_status(project.project_id, ProjectStatus.GEOMETRY_VERIFIED)
    resolved = await project_store.get(project.project_id, organisation_id=authenticated_user.organisation_id)
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

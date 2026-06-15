"""
tests/integration/api/test_artifacts_router.py
==============================================
Integration tests for the artifacts router and the Gate-1 snapshot hook.

These tests run fully in-memory: the authentication dependency is overridden
with a stub user so no real database / JWT is required, and both the project and
artifact stores use their memory backends.

Covers:
1. GET /artifacts/{project_id} — empty list, populated list, content omitted.
2. GET /artifacts/detail/{artifact_id} — full content, 404 for unknown ID.
3. PUT /files/{project_id}/verify — confirming geometry creates a VERIFICATION
   artifact attributed to the current user.
"""

from __future__ import annotations

import uuid

import pytest

from main import app
from auth.dependencies import current_active_user
from db.models.user import User
from services.files import file_service
from storage.project_store import project_store
from schemas.project import ProjectCreate, ProjectStatus


# ── Auth override ─────────────────────────────────────────────────────────────

TEST_USER = User(
    id=uuid.uuid4(),
    email="engineer@example.com",
    hashed_password="x",
    is_active=True,
    is_verified=True,
    organisation_id="test-org-id",
)


@pytest.fixture(autouse=True)
def override_auth():
    """Bypass JWT auth with a stub user for every test in this module."""
    app.dependency_overrides[current_active_user] = lambda: TEST_USER
    yield
    app.dependency_overrides.pop(current_active_user, None)


# ── Helpers ───────────────────────────────────────────────────────────────────

GEOMETRY = {
    "members": [
        {"member_id": "B-01", "member_type": "beam"},
        {"member_id": "C-01", "member_type": "column"},
    ],
    "scale": {"factor": 1.0, "unit": "mm", "confirmed": True},
}


async def _make_file_uploaded_project() -> str:
    """Create a project, register geometry, and advance it to FILE_UPLOADED."""
    project = await project_store.create(
        ProjectCreate(
            name="Artifacts Test",
            reference="ART-REF-1",
            client="Test Client",
            design_code="BS8110",
        ),
        organisation_id=TEST_USER.organisation_id,
    )
    await file_service.register_geometry(project.project_id, GEOMETRY)
    await project_store.advance_status(project.project_id, ProjectStatus.FILE_UPLOADED)
    return project.project_id


# ── List endpoint ─────────────────────────────────────────────────────────────


class TestListArtifacts:
    async def test_empty_for_new_project(self, async_client, test_project):
        resp = await async_client.get(f"/api/v1/artifacts/{test_project['project_id']}")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_unknown_project_returns_404(self, async_client):
        resp = await async_client.get("/api/v1/artifacts/PRJ-DOESNOTEXIST")
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "PROJECT_NOT_FOUND"

    async def test_lists_artifact_after_verification(self, async_client):
        project_id = await _make_file_uploaded_project()

        verify = await async_client.put(
            f"/api/v1/files/{project_id}/verify", json={"confirmed": True}
        )
        assert verify.status_code == 200

        resp = await async_client.get(f"/api/v1/artifacts/{project_id}")
        assert resp.status_code == 200
        artifacts = resp.json()
        assert len(artifacts) == 1

        card = artifacts[0]
        assert card["stage"] == "verification"
        assert card["status"] == "signed_off"
        assert card["author"] == TEST_USER.email
        assert card["content"] is None  # content omitted from list responses
        assert card["download_url"].endswith(card["artifact_id"])


# ── Detail endpoint ───────────────────────────────────────────────────────────


class TestGetArtifactDetail:
    async def test_returns_full_content(self, async_client):
        project_id = await _make_file_uploaded_project()
        await async_client.put(
            f"/api/v1/files/{project_id}/verify", json={"confirmed": True}
        )
        artifact_id = (
            await async_client.get(f"/api/v1/artifacts/{project_id}")
        ).json()[0]["artifact_id"]

        resp = await async_client.get(f"/api/v1/artifacts/detail/{artifact_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["artifact_id"] == artifact_id
        assert body["content"] is not None
        assert body["content"]["members"][0]["member_id"] == "B-01"

    async def test_unknown_artifact_returns_404(self, async_client):
        resp = await async_client.get("/api/v1/artifacts/detail/ART-NOPE")
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "ARTIFACT_NOT_FOUND"


# ── Verify hook ───────────────────────────────────────────────────────────────


class TestVerifyCreatesArtifact:
    async def test_verify_returns_artifact_id(self, async_client):
        project_id = await _make_file_uploaded_project()

        resp = await async_client.put(
            f"/api/v1/files/{project_id}/verify", json={"confirmed": True}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "verified"

    async def test_rejected_verification_creates_no_artifact(self, async_client):
        project_id = await _make_file_uploaded_project()

        resp = await async_client.put(
            f"/api/v1/files/{project_id}/verify", json={"confirmed": False}
        )
        assert resp.status_code == 400

        artifacts = (await async_client.get(f"/api/v1/artifacts/{project_id}")).json()
        assert artifacts == []

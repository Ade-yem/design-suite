"""
tests/integration/api/test_drawings_export.py
==============================================
Integration tests for the DXF export endpoints on the drawings router:

* GET /api/v1/drawings/{project_id}/export/dxf            — whole project
* GET /api/v1/drawings/{project_id}/member/{id}/export/dxf — single member

Runs fully in-memory: auth is overridden with a stub user, the project store
uses its memory backend, and drawings are seeded directly via the service.
"""
from __future__ import annotations

import uuid

import pytest

from main import app
from auth.dependencies import current_active_user
from db.models.user import User
from services.drawings import drawing_service
from storage.project_store import project_store
from schemas.project import ProjectCreate


TEST_USER = User(
    id=uuid.uuid4(),
    email="drafter@example.com",
    hashed_password="x",
    is_active=True,
    is_verified=True,
    organisation_id="test-org-id",
)


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[current_active_user] = lambda: TEST_USER
    yield
    app.dependency_overrides.pop(current_active_user, None)


def _drawing(member_id: str) -> dict:
    return {
        "member_id": member_id,
        "member_type": "beam",
        "commands": {
            "section": [
                {"type": "rect", "x": 0, "y": 0, "width": 300, "height": 600, "style": "concrete"},
                {"type": "circle", "cx": 50, "cy": 550, "r": 10, "style": "rebar"},
            ],
            "elevation": [
                {"type": "line", "x1": 0, "y1": 0, "x2": 6000, "y2": 0, "style": "bar", "diameter": 20},
            ],
            "dimensions": [
                {"type": "dimension", "axis": "horizontal", "value": 6000, "label": "6000", "x": 3000, "y": 700},
            ],
            "bar_marks": [{"type": "text", "text": "3H20", "x": 2800, "y": -100}],
            "annotations": [],
            "canvas_bounds": {"width": 6000, "height": 800},
            "scale": 20,
        },
    }


async def _make_project_with_drawings(member_ids: list[str]) -> str:
    project = await project_store.create(
        ProjectCreate(
            name="DXF Export Test",
            reference="DXF-REF-1",
            client="Test Client",
            design_code="BS8110",
        ),
        organisation_id=TEST_USER.organisation_id,
    )
    await drawing_service.save_drawings(
        project.project_id, [_drawing(mid) for mid in member_ids]
    )
    return project.project_id


class TestProjectDXFExport:
    async def test_returns_dxf_attachment(self, async_client):
        project_id = await _make_project_with_drawings(["B1", "B2"])

        resp = await async_client.get(f"/api/v1/drawings/{project_id}/export/dxf")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/vnd.dxf")
        assert "attachment" in resp.headers["content-disposition"]
        assert resp.headers["content-disposition"].endswith('.dxf"')
        # Valid ASCII DXF starts with a SECTION and carries our custom layers.
        body = resp.content.decode("utf-8", errors="ignore")
        assert "SECTION" in body
        assert "STRUCT-SECTION" in body

    async def test_404_when_no_drawings(self, async_client, test_project):
        resp = await async_client.get(
            f"/api/v1/drawings/{test_project['project_id']}/export/dxf"
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "NO_DRAWINGS"


class TestMemberDXFExport:
    async def test_returns_single_member_dxf(self, async_client):
        project_id = await _make_project_with_drawings(["B1", "B2"])

        resp = await async_client.get(
            f"/api/v1/drawings/{project_id}/member/B1/export/dxf"
        )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/vnd.dxf")
        assert "B1.dxf" in resp.headers["content-disposition"]
        assert b"SECTION" in resp.content

    async def test_unknown_member_returns_404(self, async_client):
        project_id = await _make_project_with_drawings(["B1"])

        resp = await async_client.get(
            f"/api/v1/drawings/{project_id}/member/NOPE/export/dxf"
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "MEMBER_NOT_FOUND"

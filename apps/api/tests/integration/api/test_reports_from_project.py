"""
tests/integration/api/test_reports_from_project.py
==================================================
Integration tests for ``POST /api/v1/reports/{project_id}/from-project`` — the
server-side report assembly that joins stored loading/analysis/design results
into a report without the client shipping the full member payload.

The PDF (WeasyPrint) path is not exercised here; tests use ``fmt=html`` so they
run without WeasyPrint's system libraries. The HTML render path covers the
assembly + reporting modules end to end.
"""
from __future__ import annotations

import uuid

import pytest

from main import app
from auth.dependencies import current_active_user
from db.models.user import User
from storage.project_store import project_store
from storage.stage_result_store import stage_result_store
from schemas.project import ProjectCreate
from core.design.rc import design_member


TEST_USER = User(
    id=uuid.uuid4(),
    email="reporter@example.com",
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


def _beam_design_output() -> dict:
    """A real design_member result for a beam (carries notes/status/rebar)."""
    analysis = {
        "member_id": "B1",
        "member_type": "beam",
        "stress_resultants": {
            "M_max_sagging_kNm": 120.0,
            "M_max_hogging_kNm": 0.0,
            "V_max_kN": 90.0,
            "N_axial_kN": 0.0,
        },
    }
    result = design_member(analysis, {"member_type": "beam", "b_mm": 300, "h_mm": 600}, "BS8110")
    return result


async def _make_project_with_results() -> str:
    project = await project_store.create(
        ProjectCreate(
            name="Report Assembly Test",
            reference="RPT-REF-1",
            client="Acme",
            design_code="BS8110",
        ),
        organisation_id=TEST_USER.organisation_id,
    )
    pid = project.project_id
    design = _beam_design_output()
    # Seed stored stage results the assembler reads from.
    stage_result_store._memory_store[(pid, "design")] = {
        "members": [design],
        "design_code": "BS8110",
    }
    stage_result_store._memory_store[(pid, "analysis")] = {
        "members": [{"member_id": "B1", "member_type": "beam", "stress_resultants": {}}],
    }
    stage_result_store._memory_store[(pid, "loads")] = {
        "output": {"members": [{"member_id": "B1", "spans": []}]},
    }
    return pid


class TestGenerateProjectReport:
    async def test_assembles_and_returns_report_id(self, async_client):
        pid = await _make_project_with_results()

        resp = await async_client.post(
            f"/api/v1/reports/{pid}/from-project",
            params={"report_type": "calculation_sheets", "fmt": "html"},
        )

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["report_id"].startswith("RPT-")
        assert body["member_count"] == 1
        assert body["download_url"] == f"/api/v1/reports/{body['report_id']}/download"

        # The rendered HTML must be retrievable at the advertised preview URL.
        preview = await async_client.get(body["preview_url"])
        assert preview.status_code == 200
        assert "B1" in preview.text

    async def test_404_when_no_design_results(self, async_client, test_project):
        resp = await async_client.post(
            f"/api/v1/reports/{test_project['project_id']}/from-project",
            params={"fmt": "html"},
        )
        assert resp.status_code == 404

    async def test_unknown_project_returns_404(self, async_client):
        resp = await async_client.post(
            "/api/v1/reports/PRJ-NOPE/from-project", params={"fmt": "html"}
        )
        assert resp.status_code == 404

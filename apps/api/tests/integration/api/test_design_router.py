"""
tests/integration/api/test_design_router.py
============================================
HTTP-level tests for the design router focused on stage-gate enforcement and
error responses — the design phase must be locked until analysis is complete,
and results must 404 until a design has been run.
"""
from __future__ import annotations

import pytest


class TestDesignGateEnforcement:
    async def test_run_design_requires_analysis_complete(
        self, authenticated_client, test_project
    ):
        """Designing before analysis is complete must be blocked by the gate."""
        resp = await authenticated_client.post(
            f"/api/v1/design/run/{test_project['project_id']}",
            json={},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "GATE_NOT_PASSED"

    async def test_design_member_subset_requires_analysis_complete(
        self, authenticated_client, test_project
    ):
        resp = await authenticated_client.post(
            f"/api/v1/design/{test_project['project_id']}/beam",
            json={"member_ids": ["B1"]},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "GATE_NOT_PASSED"


class TestDesignResults:
    async def test_results_404_before_design_runs(
        self, authenticated_client, geometry_verified_project
    ):
        """Results endpoint passes the gate (geometry verified) but 404s with no design."""
        # Advance the project to analysis_complete so the gate allows the read.
        from storage.project_store import project_store
        from schemas.project import ProjectStatus

        pid = geometry_verified_project["project_id"]
        await project_store.advance_status(pid, ProjectStatus.LOADING_DEFINED)
        await project_store.advance_status(pid, ProjectStatus.ANALYSIS_COMPLETE)

        resp = await authenticated_client.get(f"/api/v1/design/{pid}/results")
        assert resp.status_code == 404

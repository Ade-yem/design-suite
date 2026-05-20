import pytest


class TestGateEnforcement:
    """
    Verify that every downstream endpoint rejects out-of-sequence calls.
    All tests use a freshly created project (CREATED status, no gates passed).
    """

    async def test_loading_blocks_without_geometry_verified(
        self, async_client, test_project
    ):
        """Loading endpoint must return 403 until Gate 1 is passed."""
        r = await async_client.post(
            f"/api/v1/loading/{test_project['project_id']}/define",
            json={
                "design_code": "BS8110",
                "occupancy_category": "office",
                "imposed_loads": {"floor_qk_kNm2": 3.0},
            },
        )
        assert r.status_code == 403
        assert r.json()["error_code"] == "GATE_NOT_PASSED"

    async def test_analysis_blocks_without_loading_defined(
        self, async_client, test_project
    ):
        """Analysis endpoint must return 403 until loading is defined."""
        r = await async_client.post(
            f"/api/v1/analysis/run/{test_project['project_id']}"
        )
        assert r.status_code == 403

    async def test_design_blocks_without_analysis_complete(
        self, async_client, test_project
    ):
        """Design endpoint must return 403 until analysis is complete."""
        r = await async_client.post(
            f"/api/v1/design/run/{test_project['project_id']}"
        )
        assert r.status_code == 403

    async def test_drawings_block_without_design_confirmed(
        self, async_client, test_project
    ):
        """Drawing generation must return 403 until design is confirmed."""
        r = await async_client.post(
            f"/api/v1/drawings/{test_project['project_id']}/generate"
        )
        assert r.status_code == 403


class TestLoadingToAnalysisBoundary:

    @pytest.mark.skip(reason="Needs fully populated pipeline state")
    async def test_analysis_input_matches_loading_output_schema(
        self, async_client, project_with_loads_defined
    ):
        """Loading output JSON must be consumed by the analysis engine without 422."""
        project_id = project_with_loads_defined["project_id"]
        response = await async_client.post(
            f"/api/v1/analysis/run/{project_id}",
            json={"pattern_loading": True},
        )
        assert response.status_code in [200, 202]

    @pytest.mark.skip(reason="Needs fully populated pipeline state")
    async def test_analysis_results_contain_all_loaded_members(
        self, async_client, project_with_analysis_complete
    ):
        """Every member in loading output must appear in analysis results."""
        project_id = project_with_analysis_complete["project_id"]

        loading = await async_client.get(f"/api/v1/loading/{project_id}/output")
        analysis = await async_client.get(f"/api/v1/analysis/{project_id}/results")

        loading_ids = {m["member_id"] for m in loading.json()["data"]["members"]}
        analysis_ids = {m["member_id"] for m in analysis.json()["data"]["members"]}
        assert loading_ids == analysis_ids


class TestDesignerAnalystFailureLoop:

    @pytest.mark.skip(reason="Needs mock override processing")
    async def test_failed_member_triggers_reanalysis(
        self, async_client, project_with_design_failures
    ):
        """A failed design check must allow reanalysis with a revised member size."""
        project_id = project_with_design_failures["project_id"]
        failed_member_id = project_with_design_failures["failed_member_id"]

        override_response = await async_client.put(
            f"/api/v1/design/{project_id}/member/{failed_member_id}",
            json={"parameter": "depth_mm", "value": 650},
        )
        assert override_response.status_code == 200

        rerun_response = await async_client.post(
            f"/api/v1/design/{project_id}/rerun/{failed_member_id}"
        )
        assert rerun_response.json()["data"]["status"] == "PASS"

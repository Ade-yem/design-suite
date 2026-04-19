import pytest

class TestLoadingToAnalysisBoundary:

    @pytest.mark.skip(reason="Needs fully populated pipeline mock")
    async def test_analysis_input_matches_loading_output_schema(
        self, async_client, project_with_loads_defined
    ):
        """
        The loading output JSON must be consumed by the analysis engine
        without schema errors. This validates the inter-module contract.
        """
        project_id = project_with_loads_defined['project_id']

        response = await async_client.post(
            f"/api/v1/analysis/{project_id}/run",
            json={"pattern_loading": True}
        )

        # Must not return 422 — schema contract is satisfied
        assert response.status_code in [200, 202]

    @pytest.mark.skip(reason="Needs fully populated pipeline mock")
    async def test_analysis_results_contain_all_loaded_members(
        self, async_client, project_with_analysis_complete
    ):
        """
        Every member in the loading output must appear in analysis results.
        No member should be silently dropped.
        """
        project_id = project_with_analysis_complete['project_id']

        loading = await async_client.get(
            f"/api/v1/loading/{project_id}/output"
        )
        analysis = await async_client.get(
            f"/api/v1/analysis/{project_id}/results"
        )

        loading_member_ids = {m['member_id']
                              for m in loading.json()['data']['members']}
        analysis_member_ids = {m['member_id']
                               for m in analysis.json()['data']['members']}

        assert loading_member_ids == analysis_member_ids

class TestGateEnforcement:

    @pytest.mark.skip(reason="Depends on dynamic project creation util")
    async def test_all_gates_block_out_of_sequence_calls(self, async_client):
        """
        Systematically verify that every downstream endpoint rejects
        requests when the required upstream gate has not been passed.
        """
        project_id = "new_proj_123"

        # Analysis without geometry verified
        r = await async_client.post(f"/api/v1/analysis/{project_id}/run")
        assert r.status_code == 403

        # Design without analysis complete
        r = await async_client.post(f"/api/v1/design/{project_id}/run")
        assert r.status_code == 403

        # Drawing generation without design confirmed
        r = await async_client.post(f"/api/v1/drawings/{project_id}/generate")
        assert r.status_code == 403

        # Report without drawings confirmed
        r = await async_client.post(f"/api/v1/reports/{project_id}/generate",
                                    json={"report_type": "full"})
        assert r.status_code == 403


class TestDesignerAnalystFailureLoop:

    @pytest.mark.skip(reason="Depends on mock override processing")
    async def test_failed_member_triggers_reanalysis(
        self, async_client, project_with_design_failures
    ):
        """
        When a member fails design checks, the system must:
        1. Flag the member as failed
        2. Allow reanalysis with revised member sizes
        3. Re-run design on the revised member
        4. Not affect passing members
        """
        project_id = project_with_design_failures['project_id']
        failed_member_id = project_with_design_failures['failed_member_id']

        # Apply size increase override
        override_response = await async_client.put(
            f"/api/v1/design/{project_id}/member/{failed_member_id}",
            json={"parameter": "depth_mm", "value": 650}
        )
        assert override_response.status_code == 200

        # Rerun design for this member
        rerun_response = await async_client.post(
            f"/api/v1/design/{project_id}/rerun/{failed_member_id}"
        )

        result = rerun_response.json()['data']
        assert result['status'] == 'PASS'

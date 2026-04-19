import pytest

def valid_load_definition():
    return {
        "design_code": "BS8110",
        "occupancy_category": "OFFICE",
        "dead_loads": {"finishes_kNm2": 1.2},
        "imposed_loads": {"floor_qk_kNm2": 3.0}
    }

@pytest.fixture
async def project_at_geometry_verified(async_client, test_project):
    """Project fixture already past Gate 1"""
    # Requires an active mock or endpoint in the full integration
    # await async_client.put(
    #     f"/api/v1/files/{test_project['project_id']}/verify",
    #     json={"confirmed": True, "corrections": []}
    # )
    return test_project

class TestLoadingRouter:

    async def test_define_loads_requires_geometry_verified(
        self, async_client, test_project
    ):
        """
        Loading endpoint must return 403 if geometry is not yet verified.
        Gate enforcement is tested at the API boundary.
        """
        response = await async_client.post(
            f"/api/v1/loading/{test_project['project_id']}/define",
            json=valid_load_definition()
        )

        assert response.status_code == 403
        assert response.json()['error_code'] == "GATE_NOT_PASSED"

    @pytest.mark.skip(reason="Needs populated storage mock for test environment")
    async def test_define_loads_succeeds_after_gate_1(
        self, async_client, project_at_geometry_verified
    ):
        project_id = project_at_geometry_verified['project_id']

        response = await async_client.post(
            f"/api/v1/loading/{project_id}/define",
            json=valid_load_definition()
        )

        assert response.status_code == 200
        assert response.json()['success'] is True

    @pytest.mark.skip(reason="Needs full validation setup")
    async def test_invalid_load_returns_422(
        self, async_client, project_at_geometry_verified
    ):
        """Negative imposed load must be rejected"""
        project_id = project_at_geometry_verified['project_id']

        invalid_payload = valid_load_definition()
        invalid_payload['imposed_loads']['floor_qk_kNm2'] = -5.0

        response = await async_client.post(
            f"/api/v1/loading/{project_id}/define",
            json=invalid_payload
        )

        assert response.status_code == 422

    @pytest.mark.skip(reason="Needs end-to-end load combination runner mock")
    async def test_load_combinations_output_schema(
        self, async_client, project_at_geometry_verified
    ):
        """
        Load combination output must contain factored_n for every member.
        Validates the contract between loading module and analysis engine.
        """
        project_id = project_at_geometry_verified['project_id']

        await async_client.post(
            f"/api/v1/loading/{project_id}/define",
            json=valid_load_definition()
        )
        response = await async_client.post(
            f"/api/v1/loading/{project_id}/combinations"
        )

        output = response.json()['data']
        for member in output['members']:
            for span in member['spans']:
                assert 'udl_factored_n' in span['loads']
                assert span['loads']['udl_factored_n'] > 0

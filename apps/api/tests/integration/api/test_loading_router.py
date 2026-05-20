import pytest


def valid_load_definition():
    return {
        "design_code": "BS8110",
        "occupancy_category": "office",
        "dead_loads": {"finishes_kNm2": 1.2},
        "imposed_loads": {"floor_qk_kNm2": 3.0},
    }


class TestLoadingRouter:

    async def test_define_loads_requires_geometry_verified(
        self, async_client, test_project
    ):
        """Gate 1 must be passed before loading can be defined; expect 403."""
        response = await async_client.post(
            f"/api/v1/loading/{test_project['project_id']}/define",
            json=valid_load_definition(),
        )
        assert response.status_code == 403
        assert response.json()["error_code"] == "GATE_NOT_PASSED"

    async def test_define_loads_succeeds_after_gate_1(
        self, async_client, geometry_verified_project
    ):
        """Posting a valid load definition after Gate 1 must return 201."""
        response = await async_client.post(
            f"/api/v1/loading/{geometry_verified_project['project_id']}/define",
            json=valid_load_definition(),
        )
        assert response.status_code == 201

    async def test_invalid_load_returns_422(
        self, async_client, geometry_verified_project
    ):
        """Negative imposed load (floor_qk_kNm2 < 0) must be rejected with 422."""
        invalid_payload = valid_load_definition()
        invalid_payload["imposed_loads"]["floor_qk_kNm2"] = -5.0

        response = await async_client.post(
            f"/api/v1/loading/{geometry_verified_project['project_id']}/define",
            json=invalid_payload,
        )
        assert response.status_code == 422

    @pytest.mark.skip(reason="Needs end-to-end load combination runner")
    async def test_load_combinations_output_schema(
        self, async_client, geometry_verified_project
    ):
        """Load combination output must contain factored_n for every member."""
        project_id = geometry_verified_project["project_id"]

        await async_client.post(
            f"/api/v1/loading/{project_id}/define",
            json=valid_load_definition(),
        )
        response = await async_client.post(f"/api/v1/loading/{project_id}/combinations")

        output = response.json()["data"]
        for member in output["members"]:
            for span in member["spans"]:
                assert "udl_factored_n" in span["loads"]
                assert span["loads"]["udl_factored_n"] > 0

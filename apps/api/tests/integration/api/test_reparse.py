import pytest
from unittest.mock import AsyncMock, patch

from schemas.project import ProjectStatus
from storage.project_store import project_store
from storage.job_store import job_store
from services.files import file_service


class TestReparseRouter:

    async def test_reparse_requires_file_uploaded_status(
        self, authenticated_client, test_project
    ):
        """Reparsing requires the project to have at least reached FILE_UPLOADED status."""
        project_id = test_project["project_id"]
        response = await authenticated_client.post(
            f"/api/v1/files/{project_id}/reparse"
        )
        assert response.status_code == 403
        assert response.json()["error_code"] == "GATE_NOT_PASSED"

    async def test_reparse_requires_geometry_not_verified(
        self, authenticated_client, geometry_verified_project
    ):
        """Reparsing is blocked once the geometry is already verified."""
        project_id = geometry_verified_project["project_id"]
        response = await authenticated_client.post(
            f"/api/v1/files/{project_id}/reparse"
        )
        assert response.status_code == 400
        assert "verified" in response.json()["details"]["reason"]

    async def test_reparse_fails_if_already_parsing(
        self, authenticated_client, test_project
    ):
        """Reparsing fails if a parsing job is currently active for the project."""
        project_id = test_project["project_id"]
        await project_store.advance_status(project_id, ProjectStatus.FILE_UPLOADED)
        
        # Create an active parsing job
        await job_store.create("parsing", project_id=project_id)
        
        response = await authenticated_client.post(
            f"/api/v1/files/{project_id}/reparse"
        )
        assert response.status_code == 400
        assert "already in progress" in response.json()["details"]["reason"]

    async def test_reparse_fails_if_no_dxf_file(
        self, authenticated_client, test_project
    ):
        """Reparsing fails if no primary DXF file is stored for the project."""
        project_id = test_project["project_id"]
        await project_store.advance_status(project_id, ProjectStatus.FILE_UPLOADED)

        with patch("storage.file_handler.file_handler.list_files", return_value=[]):
            response = await authenticated_client.post(
                f"/api/v1/files/{project_id}/reparse"
            )
            assert response.status_code == 404
            assert "No primary DXF drawing file found" in response.json()["details"]["reason"]

    async def test_reparse_happy_path(
        self, authenticated_client, test_project
    ):
        """Reparsing successfully clears state, schedules background task, and returns 202."""
        project_id = test_project["project_id"]
        await project_store.advance_status(project_id, ProjectStatus.FILE_UPLOADED)

        # Mock existing uploaded files
        mock_files = ["123456_layout.dxf", "123456_ref.pdf"]
        
        # Mock some previously registered members to verify they get cleared
        await project_store.register_members_batch(project_id, ["B01", "C02"])
        member_ids_before = await project_store.get_member_ids(project_id)
        assert len(member_ids_before) == 2

        with patch("storage.file_handler.file_handler.list_files", return_value=mock_files), \
             patch("storage.file_handler.file_handler.get_url", side_effect=lambda pid, fname: f"/mock/path/{fname}"), \
             patch("routers.files._parse_file_background", new_callable=AsyncMock) as mock_bg_task:

            response = await authenticated_client.post(
                f"/api/v1/files/{project_id}/reparse"
            )
            
            assert response.status_code == 202
            data = response.json()
            assert "job_id" in data
            assert "status_url" in data
            
            # Verify registered members got cleared immediately
            member_ids_after = await project_store.get_member_ids(project_id)
            assert len(member_ids_after) == 0

            # Verify background task was scheduled with correct parameters
            mock_bg_task.assert_called_once_with(
                project_id=project_id,
                file_path="/mock/path/123456_layout.dxf",
                job_id=data["job_id"],
                pdf_path="/mock/path/123456_ref.pdf",
            )

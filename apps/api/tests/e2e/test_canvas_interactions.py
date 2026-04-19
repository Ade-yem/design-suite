import pytest
# from playwright.async_api import async_playwright

class TestCanvasInteractions:

    @pytest.mark.skip(reason="Needs Playwright UI end-to-end configuration")
    async def test_member_click_shows_properties_panel(self, live_server):
        """
        Clicking a beam on the canvas must open its properties panel
        showing section dimensions and reinforcement details.
        """
        pass

    @pytest.mark.skip(reason="Needs Playwright UI end-to-end configuration")
    async def test_layer_toggle_shows_correct_members(self, live_server):
        """
        Toggling the Structural layer off must hide structural members.
        Toggling Architectural layer must show original DXF lines.
        """
        pass

    @pytest.mark.skip(reason="Needs Playwright UI end-to-end configuration")
    async def test_confirm_button_advances_pipeline(self, live_server):
        """
        Clicking the Confirm Geometry button in the chat panel must
        advance the pipeline status from FILE_UPLOADED to GEOMETRY_VERIFIED
        """
        pass

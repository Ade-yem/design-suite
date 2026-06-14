"""
services/drawings.py
====================
Drawing service — owns all generated drawing data for a project.

This service is the single source of truth for generated 2D structural details.
It delegates persistence to stage_result_store.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from storage.stage_result_store import stage_result_store

logger = logging.getLogger(__name__)


class DrawingService:
    """
    Service for managing generated drawings.
    """

    async def list_drawings(self, project_id: str) -> list[dict[str, Any]]:
        """
        List all drawings for a project.

        Parameters
        ----------
        project_id : str

        Returns
        -------
        list[dict[str, Any]]
        """
        payload = await stage_result_store.get(project_id, "drawings")
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict) and "drawings" in payload:
            return payload["drawings"]
        return []

    async def get_drawing(self, project_id: str, member_id: str) -> Optional[dict[str, Any]]:
        """
        Retrieve a specific member's drawing.

        Parameters
        ----------
        project_id : str
        member_id : str

        Returns
        -------
        dict[str, Any] | None
        """
        drawings = await self.list_drawings(project_id)
        for drawing in drawings:
            if drawing.get("member_id") == member_id:
                return drawing
        return None

    async def save_drawings(self, project_id: str, drawings: list[dict[str, Any]]) -> None:
        """
        Save all drawings for a project.

        Parameters
        ----------
        project_id : str
        drawings : list[dict[str, Any]]
        """
        await stage_result_store.save(project_id, "drawings", drawings)

    async def clear(self, project_id: str) -> None:
        """
        Clear all drawings for a project.

        Parameters
        ----------
        project_id : str
        """
        await stage_result_store.clear(project_id, "drawings")


drawing_service = DrawingService()

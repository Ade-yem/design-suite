"""
storage/stage_result_store.py
=============================
Pluggable store for structural design pipeline stage results.

Supports dual backend behavior:
- If PROJECT_STORE_BACKEND is "memory", stores state in-process.
- If PROJECT_STORE_BACKEND is "postgres", persists serialized JSON in
  the `pipeline_results` table.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy import select, delete

from config import settings
from db.session import get_session_maker
from db.models.pipeline_results import PipelineResult

logger = logging.getLogger(__name__)


class StageResultStore:
    """
    Central storage interface for all pipeline stage results.
    """

    def __init__(self) -> None:
        self._memory_store: dict[tuple[str, str], dict[str, Any]] = {}

    async def save(self, project_id: str, stage: str, payload: dict[str, Any]) -> None:
        """
        Save the payload for a given project and stage.

        Parameters
        ----------
        project_id : str
            The project identifier (e.g. PRJ-XXXX).
        stage : str
            The pipeline stage name (e.g. 'geometry', 'loads', 'analysis', 'design', 'drawings').
        payload : dict
            The state dictionary to persist.
        """
        if not project_id:
            raise ValueError("project_id must not be empty.")
        if not stage:
            raise ValueError("stage must not be empty.")

        # Always update the local cache
        self._memory_store[(project_id, stage)] = payload

        if settings.PROJECT_STORE_BACKEND != "postgres":
            return

        try:
            session_maker = get_session_maker()
            async with session_maker() as session:
                stmt = select(PipelineResult).where(
                    PipelineResult.project_id == project_id,
                    PipelineResult.stage == stage
                )
                row = (await session.execute(stmt)).scalar_one_or_none()

                payload_str = json.dumps(payload)
                now = datetime.now(timezone.utc)

                if row:
                    row.payload = payload_str
                    row.updated_at = now
                else:
                    session.add(PipelineResult(
                        project_id=project_id,
                        stage=stage,
                        payload=payload_str,
                        updated_at=now
                    ))
                await session.commit()
        except RuntimeError:
            # Occurs when DATABASE_URL is not configured (e.g., test environment)
            pass
        except Exception as exc:
            logger.warning(
                "Failed to save stage result to PostgreSQL (project: %s, stage: %s): %s",
                project_id, stage, exc
            )

    async def get(self, project_id: str, stage: str) -> Optional[dict[str, Any]]:
        """
        Retrieve the payload for a given project and stage.
        Loads from PostgreSQL database if missing from the local cache.

        Parameters
        ----------
        project_id : str
            The project identifier.
        stage : str
            The pipeline stage name.

        Returns
        -------
        dict | None
            The persisted payload, or None if not found.
        """
        if not project_id:
            raise ValueError("project_id must not be empty.")
        if not stage:
            raise ValueError("stage must not be empty.")

        key = (project_id, stage)
        if key in self._memory_store:
            return self._memory_store[key]

        if settings.PROJECT_STORE_BACKEND != "postgres":
            return None

        try:
            session_maker = get_session_maker()
            async with session_maker() as session:
                stmt = select(PipelineResult).where(
                    PipelineResult.project_id == project_id,
                    PipelineResult.stage == stage
                )
                row = (await session.execute(stmt)).scalar_one_or_none()
                if row and row.payload:
                    payload = json.loads(row.payload)
                    self._memory_store[key] = payload
                    return payload
        except Exception as exc:
            logger.warning(
                "Failed to retrieve stage result from PostgreSQL (project: %s, stage: %s): %s",
                project_id, stage, exc
            )
        return None

    async def clear(self, project_id: str, stage: Optional[str] = None) -> None:
        """
        Clear saved stage results for a project.

        Parameters
        ----------
        project_id : str
            The project identifier.
        stage : str | None
            If provided, clears only that specific stage. Otherwise clears all stages.
        """
        if not project_id:
            raise ValueError("project_id must not be empty.")

        if stage:
            self._memory_store.pop((project_id, stage), None)
        else:
            keys_to_remove = [k for k in self._memory_store.keys() if k[0] == project_id]
            for k in keys_to_remove:
                self._memory_store.pop(k, None)

        if settings.PROJECT_STORE_BACKEND != "postgres":
            return

        try:
            session_maker = get_session_maker()
            async with session_maker() as session:
                if stage:
                    stmt = delete(PipelineResult).where(
                        PipelineResult.project_id == project_id,
                        PipelineResult.stage == stage
                    )
                else:
                    stmt = delete(PipelineResult).where(
                        PipelineResult.project_id == project_id
                    )
                await session.execute(stmt)
                await session.commit()
        except RuntimeError:
            pass
        except Exception as exc:
            logger.warning(
                "Failed to clear stage results from PostgreSQL (project: %s): %s",
                project_id, exc
            )


# Singleton instance
stage_result_store = StageResultStore()

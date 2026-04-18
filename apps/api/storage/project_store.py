"""
storage/project_store.py
========================
In-process project persistence layer.

In development this is a plain dict-backed store that lives for the lifetime of
the server process.  In production, replace the ``_store`` dict with a proper
database session (PostgreSQL via SQLAlchemy, or Redis if sub-second latency is
required for status checks).

The store owns the **project state machine** — it is the single source of truth
for ``pipeline_status`` and is the only place status transitions are written.

Public interface
----------------
ProjectStore.create(data)                 → ProjectResponse
ProjectStore.get(project_id)              → ProjectResponse | None
ProjectStore.list_all()                   → list[ProjectListItem]
ProjectStore.update(project_id, data)     → ProjectResponse | None
ProjectStore.delete(project_id)           → bool
ProjectStore.advance_status(project_id, new_status) → ProjectResponse
ProjectStore.get_or_404(project_id)       → ProjectResponse  (raises StructuralError)
ProjectStore.register_member(project_id, member_id) → None
ProjectStore.remove_member(project_id, member_id)   → None
ProjectStore.get_member_ids(project_id)   → list[str]
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import status as http_status

from middleware.error_handler import StructuralError
from schemas.project import (
    ProjectCreate,
    ProjectListItem,
    ProjectResponse,
    ProjectStatus,
    ProjectUpdate,
)


class ProjectStore:
    """
    Thread-safe (single-process) in-memory project repository.

    Attributes
    ----------
    _projects : dict[str, dict]
        Internal storage keyed by project_id.
    _members : dict[str, set[str]]
        Maps project_id → set of registered member IDs.
    """

    def __init__(self) -> None:
        self._projects: dict[str, dict] = {}
        self._members: dict[str, set[str]] = {}

    # ── CRUD ────────────────────────────────────────────────────────────────

    def create(self, data: ProjectCreate) -> ProjectResponse:
        """
        Create a new project and persist it to the in-memory store.

        Parameters
        ----------
        data : ProjectCreate
            Validated project creation payload.

        Returns
        -------
        ProjectResponse
            The fully-populated project entity with generated ``project_id``.
        """
        project_id = f"PRJ-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc)
        record = {
            "project_id": project_id,
            "name": data.name,
            "reference": data.reference,
            "client": data.client,
            "design_code": data.design_code,
            "pipeline_status": ProjectStatus.CREATED,
            "created_at": now,
            "updated_at": now,
        }
        self._projects[project_id] = record
        self._members[project_id] = set()
        return self._to_response(record)

    def get(self, project_id: str) -> Optional[ProjectResponse]:
        """
        Retrieve a project by ID.

        Parameters
        ----------
        project_id : str
            Project identifier.

        Returns
        -------
        ProjectResponse | None
            The project, or None if not found.
        """
        record = self._projects.get(project_id)
        if record is None:
            return None
        return self._to_response(record)

    def get_or_404(self, project_id: str) -> ProjectResponse:
        """
        Retrieve a project or raise a ``StructuralError`` with
        ``error_code = "PROJECT_NOT_FOUND"`` and HTTP 404.

        Parameters
        ----------
        project_id : str
            Project identifier.

        Returns
        -------
        ProjectResponse
            The project.

        Raises
        ------
        StructuralError
            If the project does not exist.
        """
        project = self.get(project_id)
        if project is None:
            raise StructuralError(
                error_code="PROJECT_NOT_FOUND",
                details={"project_id": project_id},
                status_code=http_status.HTTP_404_NOT_FOUND,
            )
        return project

    def list_all(self) -> list[ProjectListItem]:
        """
        Return lightweight summaries of all projects, ordered by most recently updated.

        Returns
        -------
        list[ProjectListItem]
            Sorted list of project summaries.
        """
        items = [
            ProjectListItem(
                project_id=r["project_id"],
                name=r["name"],
                reference=r["reference"],
                pipeline_status=r["pipeline_status"].label(),
                updated_at=r["updated_at"],
            )
            for r in self._projects.values()
        ]
        return sorted(items, key=lambda x: x.updated_at, reverse=True)

    def update(self, project_id: str, data: ProjectUpdate) -> Optional[ProjectResponse]:
        """
        Apply a partial update to an existing project.

        Parameters
        ----------
        project_id : str
            Target project identifier.
        data : ProjectUpdate
            Fields to update (only non-None fields are applied).

        Returns
        -------
        ProjectResponse | None
            Updated project, or None if project does not exist.
        """
        record = self._projects.get(project_id)
        if record is None:
            return None
        if data.name is not None:
            record["name"] = data.name
        if data.reference is not None:
            record["reference"] = data.reference
        if data.client is not None:
            record["client"] = data.client
        if data.design_code is not None:
            record["design_code"] = data.design_code
        record["updated_at"] = datetime.now(timezone.utc)
        return self._to_response(record)

    def delete(self, project_id: str) -> bool:
        """
        Delete a project and all associated member records.

        Parameters
        ----------
        project_id : str
            Target project identifier.

        Returns
        -------
        bool
            True if deleted, False if not found.
        """
        if project_id not in self._projects:
            return False
        del self._projects[project_id]
        self._members.pop(project_id, None)
        return True

    # ── Status machine ───────────────────────────────────────────────────────

    def advance_status(self, project_id: str, new_status: ProjectStatus) -> ProjectResponse:
        """
        Advance the pipeline status of a project.

        The new status must be **greater than or equal to** the current status
        (never step backwards).

        Parameters
        ----------
        project_id : str
            Target project identifier.
        new_status : ProjectStatus
            Target pipeline stage.

        Returns
        -------
        ProjectResponse
            Updated project.

        Raises
        ------
        StructuralError
            If the project does not exist (PROJECT_NOT_FOUND).
        ValueError
            If ``new_status`` is less than the current status (regression attempt).
        """
        record = self._projects.get(project_id)
        if record is None:
            raise StructuralError(
                "PROJECT_NOT_FOUND",
                details={"project_id": project_id},
                status_code=http_status.HTTP_404_NOT_FOUND,
            )
        record["pipeline_status"] = new_status
        record["updated_at"] = datetime.now(timezone.utc)
        return self._to_response(record)

    def get_status(self, project_id: str) -> Optional[ProjectStatus]:
        """
        Return the current pipeline status without a full response object.

        Parameters
        ----------
        project_id : str
            Project identifier.

        Returns
        -------
        ProjectStatus | None
        """
        record = self._projects.get(project_id)
        return record["pipeline_status"] if record else None

    # ── Member tracking ──────────────────────────────────────────────────────

    def register_member(self, project_id: str, member_id: str) -> None:
        """
        Register a member ID under a project.

        Parameters
        ----------
        project_id : str
            Parent project.
        member_id : str
            Member identifier to register.
        """
        if project_id in self._members:
            self._members[project_id].add(member_id)

    def remove_member(self, project_id: str, member_id: str) -> None:
        """
        Remove a member ID from a project's member registry.

        Parameters
        ----------
        project_id : str
            Parent project.
        member_id : str
            Member to remove.
        """
        if project_id in self._members:
            self._members[project_id].discard(member_id)

    def get_member_ids(self, project_id: str) -> list[str]:
        """
        Return the set of registered member IDs for a project.

        Parameters
        ----------
        project_id : str
            Parent project.

        Returns
        -------
        list[str]
            Sorted list of member IDs.
        """
        return sorted(self._members.get(project_id, set()))

    # ── Internal ─────────────────────────────────────────────────────────────

    def _to_response(self, record: dict) -> ProjectResponse:
        """Convert an internal record dict to a ``ProjectResponse``."""
        project_id = record["project_id"]
        status: ProjectStatus = record["pipeline_status"]
        return ProjectResponse(
            project_id=project_id,
            name=record["name"],
            reference=record["reference"],
            client=record["client"],
            design_code=record["design_code"],
            pipeline_status=status.label(),
            pipeline_status_ordinal=int(status),
            created_at=record["created_at"],
            updated_at=record["updated_at"],
            member_count=len(self._members.get(project_id, set())),
        )


# ── Singleton ────────────────────────────────────────────────────────────────
project_store = ProjectStore()

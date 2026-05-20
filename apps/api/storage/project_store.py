"""
storage/project_store.py
========================
Pluggable project persistence layer.

Supports two backends controlled by ``settings.PROJECT_STORE_BACKEND``:
- ``"memory"``   — in-process dict store (development / testing)
- ``"postgres"`` — async SQLAlchemy store backed by PostgreSQL

The public interface is identical for both backends (all methods are
``async def``) so routers and agents call ``await project_store.<method>()``
regardless of the active backend.

Public interface
----------------
create(data)                              → ProjectResponse
get(project_id)                           → ProjectResponse | None
get_or_404(project_id)                    → ProjectResponse
list_all()                                → list[ProjectListItem]
update(project_id, data)                  → ProjectResponse | None
delete(project_id)                        → bool
advance_status(project_id, new_status)    → ProjectResponse
get_status(project_id)                    → ProjectStatus | None
register_member(project_id, member_id)    → None
remove_member(project_id, member_id)      → None
get_member_ids(project_id)                → list[str]
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


# ── In-memory implementation ──────────────────────────────────────────────────


class MemoryProjectStore:
    """
    In-process in-memory project repository.

    All methods are ``async def`` with synchronous bodies so they can be
    awaited uniformly by callers without importing asyncio.

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

    # ── CRUD ─────────────────────────────────────────────────────────────────

    async def create(self, data: ProjectCreate) -> ProjectResponse:
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

    async def get(self, project_id: str) -> Optional[ProjectResponse]:
        record = self._projects.get(project_id)
        if record is None:
            return None
        return self._to_response(record)

    async def get_or_404(self, project_id: str) -> ProjectResponse:
        project = await self.get(project_id)
        if project is None:
            raise StructuralError(
                error_code="PROJECT_NOT_FOUND",
                details={"project_id": project_id},
                status_code=http_status.HTTP_404_NOT_FOUND,
            )
        return project

    async def list_all(self) -> list[ProjectListItem]:
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

    async def update(self, project_id: str, data: ProjectUpdate) -> Optional[ProjectResponse]:
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

    async def delete(self, project_id: str) -> bool:
        if project_id not in self._projects:
            return False
        del self._projects[project_id]
        self._members.pop(project_id, None)
        return True

    # ── Status machine ────────────────────────────────────────────────────────

    async def advance_status(self, project_id: str, new_status: ProjectStatus) -> ProjectResponse:
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

    async def get_status(self, project_id: str) -> Optional[ProjectStatus]:
        record = self._projects.get(project_id)
        return record["pipeline_status"] if record else None

    # ── Member tracking ───────────────────────────────────────────────────────

    async def register_member(self, project_id: str, member_id: str) -> None:
        if project_id in self._members:
            self._members[project_id].add(member_id)

    async def remove_member(self, project_id: str, member_id: str) -> None:
        if project_id in self._members:
            self._members[project_id].discard(member_id)

    async def get_member_ids(self, project_id: str) -> list[str]:
        return sorted(self._members.get(project_id, set()))

    # ── Internal ──────────────────────────────────────────────────────────────

    def _to_response(self, record: dict) -> ProjectResponse:
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


# ── PostgreSQL implementation ─────────────────────────────────────────────────


class PostgresProjectStore:
    """
    PostgreSQL-backed project repository using async SQLAlchemy.

    Each method opens its own session via ``get_session_maker()``.
    The ``pipeline_status`` ORM column is an int; this class converts to/from
    the ``ProjectStatus`` IntEnum.
    """

    # ── CRUD ─────────────────────────────────────────────────────────────────

    async def create(self, data: ProjectCreate) -> ProjectResponse:
        from db.session import get_session_maker
        from db.models.project import Project

        project_id = f"PRJ-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc)

        session_maker = get_session_maker()
        async with session_maker() as session:
            row = Project(
                project_id=project_id,
                name=data.name,
                reference=data.reference,
                client=data.client,
                design_code=data.design_code,
                pipeline_status=int(ProjectStatus.CREATED),
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._to_response(row, member_count=0)

    async def get(self, project_id: str) -> Optional[ProjectResponse]:
        from db.session import get_session_maker
        from db.models.project import Project, ProjectMember
        from sqlalchemy import select, func

        session_maker = get_session_maker()
        async with session_maker() as session:
            row = (
                await session.execute(
                    select(Project).where(Project.project_id == project_id)
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            count = (
                await session.execute(
                    select(func.count()).where(ProjectMember.project_id == project_id)
                )
            ).scalar_one()
            return self._to_response(row, member_count=count)

    async def get_or_404(self, project_id: str) -> ProjectResponse:
        project = await self.get(project_id)
        if project is None:
            raise StructuralError(
                error_code="PROJECT_NOT_FOUND",
                details={"project_id": project_id},
                status_code=http_status.HTTP_404_NOT_FOUND,
            )
        return project

    async def list_all(self) -> list[ProjectListItem]:
        from db.session import get_session_maker
        from db.models.project import Project
        from sqlalchemy import select

        session_maker = get_session_maker()
        async with session_maker() as session:
            rows = (
                await session.execute(
                    select(Project).order_by(Project.updated_at.desc())
                )
            ).scalars().all()
            return [
                ProjectListItem(
                    project_id=r.project_id,
                    name=r.name,
                    reference=r.reference or "",
                    pipeline_status=ProjectStatus(r.pipeline_status).label(),
                    updated_at=r.updated_at,
                )
                for r in rows
            ]

    async def update(self, project_id: str, data: ProjectUpdate) -> Optional[ProjectResponse]:
        from db.session import get_session_maker
        from db.models.project import Project, ProjectMember
        from sqlalchemy import select, func

        session_maker = get_session_maker()
        async with session_maker() as session:
            row = (
                await session.execute(
                    select(Project).where(Project.project_id == project_id)
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            if data.name is not None:
                row.name = data.name
            if data.reference is not None:
                row.reference = data.reference
            if data.client is not None:
                row.client = data.client
            if data.design_code is not None:
                row.design_code = data.design_code
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(row)
            count = (
                await session.execute(
                    select(func.count()).where(ProjectMember.project_id == project_id)
                )
            ).scalar_one()
            return self._to_response(row, member_count=count)

    async def delete(self, project_id: str) -> bool:
        from db.session import get_session_maker
        from db.models.project import Project
        from sqlalchemy import select

        session_maker = get_session_maker()
        async with session_maker() as session:
            row = (
                await session.execute(
                    select(Project).where(Project.project_id == project_id)
                )
            ).scalar_one_or_none()
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    # ── Status machine ────────────────────────────────────────────────────────

    async def advance_status(self, project_id: str, new_status: ProjectStatus) -> ProjectResponse:
        from db.session import get_session_maker
        from db.models.project import Project, ProjectMember
        from sqlalchemy import select, func

        session_maker = get_session_maker()
        async with session_maker() as session:
            row = (
                await session.execute(
                    select(Project).where(Project.project_id == project_id)
                )
            ).scalar_one_or_none()
            if row is None:
                raise StructuralError(
                    "PROJECT_NOT_FOUND",
                    details={"project_id": project_id},
                    status_code=http_status.HTTP_404_NOT_FOUND,
                )
            row.pipeline_status = int(new_status)
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(row)
            count = (
                await session.execute(
                    select(func.count()).where(ProjectMember.project_id == project_id)
                )
            ).scalar_one()
            return self._to_response(row, member_count=count)

    async def get_status(self, project_id: str) -> Optional[ProjectStatus]:
        from db.session import get_session_maker
        from db.models.project import Project
        from sqlalchemy import select

        session_maker = get_session_maker()
        async with session_maker() as session:
            row = (
                await session.execute(
                    select(Project.pipeline_status).where(Project.project_id == project_id)
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return ProjectStatus(row)

    # ── Member tracking ───────────────────────────────────────────────────────

    async def register_member(self, project_id: str, member_id: str) -> None:
        from db.session import get_session_maker
        from db.models.project import ProjectMember
        from sqlalchemy import select

        session_maker = get_session_maker()
        async with session_maker() as session:
            existing = (
                await session.execute(
                    select(ProjectMember).where(
                        ProjectMember.project_id == project_id,
                        ProjectMember.member_id == member_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                # Infer structural member type from standard prefix conventions
                m_type = "beam"
                upper_id = member_id.upper()
                if upper_id.startswith("C"):
                    m_type = "column"
                elif upper_id.startswith("S"):
                    m_type = "slab"
                elif upper_id.startswith("F"):
                    m_type = "footing"
                elif upper_id.startswith("W"):
                    m_type = "wall"

                session.add(
                    ProjectMember(
                        project_id=project_id,
                        member_id=member_id,
                        member_type=m_type,
                    )
                )
                await session.commit()

    async def remove_member(self, project_id: str, member_id: str) -> None:
        from db.session import get_session_maker
        from db.models.project import ProjectMember
        from sqlalchemy import select

        session_maker = get_session_maker()
        async with session_maker() as session:
            row = (
                await session.execute(
                    select(ProjectMember).where(
                        ProjectMember.project_id == project_id,
                        ProjectMember.member_id == member_id,
                    )
                )
            ).scalar_one_or_none()
            if row is not None:
                await session.delete(row)
                await session.commit()

    async def get_member_ids(self, project_id: str) -> list[str]:
        from db.session import get_session_maker
        from db.models.project import ProjectMember
        from sqlalchemy import select

        session_maker = get_session_maker()
        async with session_maker() as session:
            rows = (
                await session.execute(
                    select(ProjectMember.member_id).where(
                        ProjectMember.project_id == project_id
                    )
                )
            ).scalars().all()
            return sorted(rows)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _to_response(self, row: object, member_count: int) -> ProjectResponse:
        status = ProjectStatus(row.pipeline_status)  # type: ignore[attr-defined]
        return ProjectResponse(
            project_id=row.project_id,  # type: ignore[attr-defined]
            name=row.name,  # type: ignore[attr-defined]
            reference=row.reference or "",  # type: ignore[attr-defined]
            client=row.client or "",  # type: ignore[attr-defined]
            design_code=row.design_code,  # type: ignore[attr-defined]
            pipeline_status=status.label(),
            pipeline_status_ordinal=int(status),
            created_at=row.created_at,  # type: ignore[attr-defined]
            updated_at=row.updated_at,  # type: ignore[attr-defined]
            member_count=member_count,
        )


def make_project_store() -> MemoryProjectStore | PostgresProjectStore:
    """Instantiate and return the configured project store backend."""
    from config import settings

    if settings.PROJECT_STORE_BACKEND == "postgres":
        if not settings.DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL must be configured in your environment or .env file "
                "when PROJECT_STORE_BACKEND is set to 'postgres'."
            )
        return PostgresProjectStore()
    return MemoryProjectStore()


project_store = make_project_store()

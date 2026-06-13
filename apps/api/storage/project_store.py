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
import logging
from fastapi import status as http_status

from middleware.error_handler import StructuralError
from schemas.project import (
    ProjectCreate,
    ProjectListItem,
    ProjectResponse,
    ProjectStatus,
    ProjectUpdate,
)


logger = logging.getLogger(__name__)

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
        self._loads: dict[str, tuple[dict, dict | None]] = {}

    async def save_loads(self, project_id: str, definition: dict, output: dict | None) -> None:
        """
        Store the load definition and output for a project in memory.

        Parameters
        ----------
        project_id : str
        definition : dict
        output : dict | None
        """
        self._loads[project_id] = (definition, output)

    async def get_loads(self, project_id: str) -> tuple[dict | None, dict | None]:
        """
        Retrieve the stored load definition and output for a project from memory.

        Parameters
        ----------
        project_id : str

        Returns
        -------
        tuple[dict | None, dict | None]
            (definition, output)
        """
        return self._loads.get(project_id, (None, None))

    # ── CRUD ─────────────────────────────────────────────────────────────────

    async def create(
        self,
        data: ProjectCreate,
        organisation_id: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> ProjectResponse:
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
            "organisation_id": organisation_id,
            "created_by": user_id,
        }
        self._projects[project_id] = record
        self._members[project_id] = set()
        return self._to_response(record)

    async def get(
        self,
        project_id: str,
        organisation_id: str | None = None,
        bypass_tenant_check: bool = False,
    ) -> Optional[ProjectResponse]:
        record = self._projects.get(project_id)
        if record is None:
            return None
        if not bypass_tenant_check:
            if organisation_id is None:
                return None
            if record.get("organisation_id") != organisation_id:
                return None
        return self._to_response(record)

    async def get_or_404(
        self,
        project_id: str,
        organisation_id: str | None = None,
        bypass_tenant_check: bool = False,
    ) -> ProjectResponse:
        project = await self.get(project_id, organisation_id, bypass_tenant_check=bypass_tenant_check)
        if project is None:
            raise StructuralError(
                error_code="PROJECT_NOT_FOUND",
                details={"project_id": project_id},
                status_code=http_status.HTTP_404_NOT_FOUND,
            )
        return project

    async def list_all(
        self, organisation_id: str | None = None, bypass_tenant_check: bool = False
    ) -> list[ProjectListItem]:
        items = []
        for r in self._projects.values():
            if not bypass_tenant_check:
                if organisation_id is None:
                    continue
                if r.get("organisation_id") != organisation_id:
                    continue
            items.append(
                ProjectListItem(
                    project_id=r["project_id"],
                    name=r["name"],
                    reference=r["reference"],
                    pipeline_status=r["pipeline_status"].label(),
                    updated_at=r["updated_at"],
                )
            )
        return sorted(items, key=lambda x: x.updated_at, reverse=True)

    async def update(
        self,
        project_id: str,
        data: ProjectUpdate,
        organisation_id: str | None = None,
        bypass_tenant_check: bool = False,
    ) -> Optional[ProjectResponse]:
        record = self._projects.get(project_id)
        if record is None:
            return None
        if not bypass_tenant_check:
            if organisation_id is None:
                return None
            if record.get("organisation_id") != organisation_id:
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

    async def delete(
        self,
        project_id: str,
        organisation_id: str | None = None,
        bypass_tenant_check: bool = False,
    ) -> bool:
        if project_id not in self._projects:
            return False
        record = self._projects[project_id]
        if not bypass_tenant_check:
            if organisation_id is None:
                return False
            if record.get("organisation_id") != organisation_id:
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

    async def register_members_batch(self, project_id: str, member_ids: list[str]) -> None:
        """
        Batch register multiple structural member IDs for a project.

        Parameters
        ----------
        project_id : str
            Project identifier.
        member_ids : list[str]
            List of member identifiers to register.
        """
        if project_id in self._members:
            self._members[project_id] = set(member_ids)

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
            organisation_id=record.get("organisation_id"),
            created_by=record.get("created_by"),
        )



# ── PostgreSQL implementation ─────────────────────────────────────────────────


class PostgresProjectStore:
    """
    PostgreSQL-backed project repository using async SQLAlchemy.

    Uses a cached session maker retrieved once in constructor.
    The ``pipeline_status`` ORM column is an int; this class converts to/from
    the ``ProjectStatus`` IntEnum.
    """

    def __init__(self) -> None:
        from db.session import get_session_maker
        self.session_maker = get_session_maker()

    # ── CRUD ─────────────────────────────────────────────────────────────────

    async def create(
        self,
        data: ProjectCreate,
        organisation_id: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> ProjectResponse:
        from db.models.project import Project

        project_id = f"PRJ-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc)

        async with self.session_maker() as session:
            row = Project(
                project_id=project_id,
                name=data.name,
                reference=data.reference,
                client=data.client,
                design_code=data.design_code,
                pipeline_status=int(ProjectStatus.CREATED),
                created_at=now,
                updated_at=now,
                organisation_id=organisation_id,
                created_by=user_id,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._to_response(row, member_count=0)

    async def get(
        self,
        project_id: str,
        organisation_id: str | None = None,
        bypass_tenant_check: bool = False,
    ) -> Optional[ProjectResponse]:
        from db.models.project import Project, ProjectMember
        from sqlalchemy import select, func

        async with self.session_maker() as session:
            stmt = select(Project).where(Project.project_id == project_id)
            if not bypass_tenant_check:
                if organisation_id is None:
                    return None
                stmt = stmt.where(Project.organisation_id == organisation_id)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            count = (
                await session.execute(
                    select(func.count()).where(ProjectMember.project_id == project_id)
                )
            ).scalar_one()
            return self._to_response(row, member_count=count)

    async def get_or_404(
        self,
        project_id: str,
        organisation_id: str | None = None,
        bypass_tenant_check: bool = False,
    ) -> ProjectResponse:
        project = await self.get(project_id, organisation_id, bypass_tenant_check=bypass_tenant_check)
        if project is None:
            raise StructuralError(
                error_code="PROJECT_NOT_FOUND",
                details={"project_id": project_id},
                status_code=http_status.HTTP_404_NOT_FOUND,
            )
        return project

    async def list_all(
        self, organisation_id: str | None = None, bypass_tenant_check: bool = False
    ) -> list[ProjectListItem]:
        from db.models.project import Project
        from sqlalchemy import select

        async with self.session_maker() as session:
            stmt = select(Project)
            if not bypass_tenant_check:
                if organisation_id is None:
                    return []
                stmt = stmt.where(Project.organisation_id == organisation_id)
            stmt = stmt.order_by(Project.updated_at.desc())
            rows = (await session.execute(stmt)).scalars().all()
            res = [
                ProjectListItem(
                    project_id=r.project_id,
                    name=r.name,
                    reference=r.reference or "",
                    pipeline_status=ProjectStatus(r.pipeline_status).label(),
                    updated_at=r.updated_at,
                )
                for r in rows
            ]
            logger.info(f"Found {len(res)} projects")
            return res

    async def update(
        self,
        project_id: str,
        data: ProjectUpdate,
        organisation_id: str | None = None,
        bypass_tenant_check: bool = False,
    ) -> Optional[ProjectResponse]:
        from db.models.project import Project, ProjectMember
        from sqlalchemy import select, func

        async with self.session_maker() as session:
            stmt = select(Project).where(Project.project_id == project_id)
            if not bypass_tenant_check:
                if organisation_id is None:
                    return None
                stmt = stmt.where(Project.organisation_id == organisation_id)
            row = (await session.execute(stmt)).scalar_one_or_none()
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

    async def delete(
        self,
        project_id: str,
        organisation_id: str | None = None,
        bypass_tenant_check: bool = False,
    ) -> bool:
        from db.models.project import Project
        from sqlalchemy import select

        async with self.session_maker() as session:
            stmt = select(Project).where(Project.project_id == project_id)
            if not bypass_tenant_check:
                if organisation_id is None:
                    return False
                stmt = stmt.where(Project.organisation_id == organisation_id)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    # ── Status machine ────────────────────────────────────────────────────────

    async def advance_status(self, project_id: str, new_status: ProjectStatus) -> ProjectResponse:
        from db.models.project import Project, ProjectMember
        from sqlalchemy import select, func

        async with self.session_maker() as session:
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
        from db.models.project import Project
        from sqlalchemy import select

        async with self.session_maker() as session:
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
        from db.models.project import ProjectMember
        from sqlalchemy import select

        async with self.session_maker() as session:
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

    async def register_members_batch(self, project_id: str, member_ids: list[str]) -> None:
        """
        Register multiple structural member IDs in a single database transaction.
        Enables bulk verification and eliminates N+1 SQL connections.

        Parameters
        ----------
        project_id : str
            Project identifier.
        member_ids : list[str]
            List of member identifiers to register.
        """
        from db.models.project import ProjectMember
        from sqlalchemy import select, delete

        async with self.session_maker() as session:
            # 1. Fetch all existing member IDs for this project in one query
            stmt = select(ProjectMember.member_id).where(ProjectMember.project_id == project_id)
            existing_rows = (await session.execute(stmt)).scalars().all()
            existing_set = set(existing_rows)
            target_set = set(member_ids)

            # 2. Delete obsolete members
            obsolete = existing_set - target_set
            if obsolete:
                del_stmt = delete(ProjectMember).where(
                    ProjectMember.project_id == project_id,
                    ProjectMember.member_id.in_(list(obsolete))
                )
                await session.execute(del_stmt)

            # 3. Filter new members and prepare batch insert
            new_members = []
            added_in_batch = set()
            for mid in member_ids:
                if mid not in existing_set and mid not in added_in_batch:
                    added_in_batch.add(mid)
                    m_type = "beam"
                    upper_id = mid.upper()
                    if upper_id.startswith("C"):
                        m_type = "column"
                    elif upper_id.startswith("S"):
                        m_type = "slab"
                    elif upper_id.startswith("F"):
                        m_type = "footing"
                    elif upper_id.startswith("W"):
                        m_type = "wall"

                    new_members.append(
                        ProjectMember(
                            project_id=project_id,
                            member_id=mid,
                            member_type=m_type,
                        )
                    )

            # 4. Add and commit all modifications in a single transaction
            if new_members:
                session.add_all(new_members)
            await session.commit()
            logger.info(
                "Batch synchronized members for project %s: deleted %d, added %d", 
                project_id,
                len(obsolete),
                len(new_members),
            )

    async def remove_member(self, project_id: str, member_id: str) -> None:
        from db.models.project import ProjectMember
        from sqlalchemy import select

        async with self.session_maker() as session:
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
        from db.models.project import ProjectMember
        from sqlalchemy import select

        async with self.session_maker() as session:
            rows = (
                await session.execute(
                    select(ProjectMember.member_id).where(
                        ProjectMember.project_id == project_id
                    )
                )
            ).scalars().all()
            return sorted(rows)

    # ── Load persistence ──────────────────────────────────────────────────────

    async def save_loads(self, project_id: str, definition: dict, output: dict | None) -> None:
        """
        Upsert the load definition and output for a project to the database.

        Parameters
        ----------
        project_id : str
        definition : dict
        output : dict | None
        """
        import json
        from db.models.project import ProjectLoad
        from sqlalchemy import select

        async with self.session_maker() as session:
            row = (await session.execute(
                select(ProjectLoad).where(ProjectLoad.project_id == project_id)
            )).scalar_one_or_none()

            def_str = json.dumps(definition)
            out_str = json.dumps(output) if output is not None else None

            if row:
                row.definition = def_str
                if out_str is not None:
                    row.output = out_str
            else:
                session.add(ProjectLoad(
                    project_id=project_id,
                    definition=def_str,
                    output=out_str,
                ))
            await session.commit()

    async def get_loads(self, project_id: str) -> tuple[dict | None, dict | None]:
        """
        Retrieve the stored load definition and output for a project from the database.

        Parameters
        ----------
        project_id : str

        Returns
        -------
        tuple[dict | None, dict | None]
            (definition, output)
        """
        import json
        from db.models.project import ProjectLoad
        from sqlalchemy import select

        async with self.session_maker() as session:
            row = (await session.execute(
                select(ProjectLoad).where(ProjectLoad.project_id == project_id)
            )).scalar_one_or_none()
            if row:
                definition = json.loads(row.definition) if row.definition else None
                output = json.loads(row.output) if row.output else None
                return definition, output
            return None, None

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
            organisation_id=row.organisation_id,  # type: ignore[attr-defined]
            created_by=row.created_by,  # type: ignore[attr-defined]
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

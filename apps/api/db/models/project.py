"""
db/models/project.py
====================
SQLAlchemy ORM model for Projects.

A Project is the top-level entity for the structural design pipeline.
Every project tracks its pipeline status through a state machine
(mirrors the in-memory ProjectStatus enum in schemas/project.py).

Each project is owned by one Organisation and optionally attributed to
the User who created it.
"""

from __future__ import annotations

from db.models.user import User
from db.models.organisation import Organisation

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Project(Base):
    """
    Persistent project record in PostgreSQL.

    Attributes
    ----------
    project_id : str
        UUID primary key.
    name : str
        Human-readable project name.
    reference : str | None
        Engineering drawing reference number.
    client : str | None
        Client name for report headers.
    design_code : str
        Active design code (``BS8110`` | ``EC2``).
    pipeline_status : int
        Integer representation of the ProjectStatus enum.
    created_at : datetime
        UTC creation timestamp.
    updated_at : datetime
        UTC last-update timestamp.
    organisation_id : str
        FK → organisations.id (tenancy owner).
    created_by : str | None
        FK → users.id (user who created the project).
    member_ids : list[ProjectMember]
        Registered structural member identifiers.
    loads : ProjectLoad | None
        Load definition and combination output.
    geometry : ProjectGeometry | None
        Parsed structural JSON and verification status.
    """

    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: f"PRJ-{uuid.uuid4().hex[:8].upper()}"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    client: Mapped[str | None] = mapped_column(String(255), nullable=True)
    design_code: Mapped[str] = mapped_column(String(20), default="BS8110")
    pipeline_status: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Tenancy / Ownership ───────────────────────────────────────────────────
    organisation_id: Mapped[str] = mapped_column(
        String, ForeignKey("organisations.id"), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(
        String, ForeignKey("users.id"), nullable=True
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    organisation: Mapped["Organisation"] = relationship(  # noqa: F821
        "Organisation", back_populates="projects"
    )
    created_by_user: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="projects"
    )
    member_ids: Mapped[list["ProjectMember"]] = relationship(
        "ProjectMember", back_populates="project", cascade="all, delete-orphan"
    )
    loads: Mapped["ProjectLoad | None"] = relationship(
        "ProjectLoad", back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    geometry: Mapped["ProjectGeometry | None"] = relationship(
        "ProjectGeometry", back_populates="project", uselist=False, cascade="all, delete-orphan"
    )


class ProjectMember(Base):
    """
    Registered structural member ID within a project.

    Attributes
    ----------
    id : int
        Auto-increment PK.
    project_id : str
        FK → projects.project_id.
    member_id : str
        Structural member identifier (e.g. ``"B01"``, ``"C02"``).
    member_type : str
        Member classification (``beam`` | ``column`` | ``slab`` | ``footing``).
    """

    __tablename__ = "project_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.project_id"), nullable=False)
    member_id: Mapped[str] = mapped_column(String(100), nullable=False)
    member_type: Mapped[str] = mapped_column(String(50), default="beam")

    project: Mapped[Project] = relationship("Project", back_populates="member_ids")


class ProjectLoad(Base):
    """
    Load definition and combination output for a project.

    Stores the raw LoadDefinitionRequest dict and the factored output
    produced by the LoadCombinationEngine as JSONB columns.

    Attributes
    ----------
    id : int
        Auto-increment PK.
    project_id : str
        FK → projects.project_id (one-to-one).
    definition : dict | None
        The submitted LoadDefinitionRequest as a JSON object.
    output : dict | None
        The factored MemberLoadOutput produced by run_combinations.
    created_at : datetime
        UTC timestamp of first submission.
    updated_at : datetime
        UTC timestamp of last update.
    """

    __tablename__ = "project_loads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String, ForeignKey("projects.project_id"), unique=True, nullable=False
    )
    definition: Mapped[dict | None] = mapped_column(Text, nullable=True)   # stored as JSON string
    output: Mapped[dict | None] = mapped_column(Text, nullable=True)       # stored as JSON string
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    project: Mapped[Project] = relationship("Project", back_populates="loads")


class ProjectGeometry(Base):
    """
    Parsed structural geometry JSON for a project (output of the Parser Agent).

    Stores the Structural JSON Schema produced after DXF/PDF parsing.
    Also records whether the human engineer has confirmed/verified the geometry
    (Safety Gate 1).

    Attributes
    ----------
    id : int
        Auto-increment PK.
    project_id : str
        FK → projects.project_id (one-to-one).
    geometry : str
        Full StructuralDesignState geometry JSON as a text string.
    verified_at : datetime | None
        UTC timestamp when the engineer confirmed the parsed geometry.
    updated_at : datetime
        UTC timestamp of last parser update.
    """

    __tablename__ = "project_geometry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String, ForeignKey("projects.project_id"), unique=True, nullable=False
    )
    geometry: Mapped[str] = mapped_column(Text, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    project: Mapped[Project] = relationship("Project", back_populates="geometry")

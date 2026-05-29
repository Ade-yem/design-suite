"""
db/models/pipeline.py
=====================
SQLAlchemy ORM models for pipeline computation results.

One-to-one with Project; each table stores the full JSON output
of its corresponding pipeline stage so results survive server restarts.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class ProjectAnalysis(Base):
    """
    Full analysis output for a project (output of AnalysisService.run).

    Attributes
    ----------
    id : int
        Auto-increment PK.
    project_id : str
        FK → projects.project_id (one-to-one).
    analysis_id : str
        Identifier echoed from the analysis run (e.g. ``"ANA-XXXX"``).
    design_code : str
        Design code used (``BS8110`` | ``EC2``).
    output : str
        Full ``AnalysisResultsResponse`` serialised as a JSON string.
    generated_at : datetime
        UTC timestamp of the analysis run.
    updated_at : datetime
        UTC timestamp of last update.
    """

    __tablename__ = "project_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String, ForeignKey("projects.project_id", ondelete="CASCADE"), unique=True, nullable=False
    )
    analysis_id: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    design_code: Mapped[str] = mapped_column(String(20), nullable=False, default="BS8110")
    output: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    project: Mapped["Project"] = relationship(  # noqa: F821
        "Project", back_populates="analysis"
    )


class ProjectDesign(Base):
    """
    Full design output for a project (output of DesignService.run).

    Attributes
    ----------
    id : int
        Auto-increment PK.
    project_id : str
        FK → projects.project_id (one-to-one).
    design_id : str
        Identifier echoed from the design run (e.g. ``"DES-XXXX"``).
    design_code : str
        Design code used (``BS8110`` | ``EC2``).
    output : str
        Full ``DesignResultsResponse`` serialised as a JSON string.
    generated_at : datetime
        UTC timestamp of the design run.
    updated_at : datetime
        UTC timestamp of last update.
    """

    __tablename__ = "project_design"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String, ForeignKey("projects.project_id", ondelete="CASCADE"), unique=True, nullable=False
    )
    design_id: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    design_code: Mapped[str] = mapped_column(String(20), nullable=False, default="BS8110")
    output: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    project: Mapped["Project"] = relationship(  # noqa: F821
        "Project", back_populates="design"
    )


class ProjectDrawing(Base):
    """
    Drawing command output for a project (output of DrafterAgent / DrawingService).

    Attributes
    ----------
    id : int
        Auto-increment PK.
    project_id : str
        FK → projects.project_id (one-to-one).
    commands : str
        Drawing primitive commands serialised as a JSON string.
    gate4_confirmed : bool
        Whether the engineer has confirmed the final drawing set (Gate 4).
    generated_at : datetime
        UTC timestamp of drawing generation.
    updated_at : datetime
        UTC timestamp of last update.
    """

    __tablename__ = "project_drawings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String, ForeignKey("projects.project_id", ondelete="CASCADE"), unique=True, nullable=False
    )
    commands: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    gate4_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    project: Mapped["Project"] = relationship(  # noqa: F821
        "Project", back_populates="drawing"
    )

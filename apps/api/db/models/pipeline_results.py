"""
db/models/pipeline_results.py
=============================
SQLAlchemy ORM model for storing stage outputs of the structural design pipeline.

A PipelineResult holds the serialized JSON payload of a specific stage
(geometry, loads, analysis, design, drawings) associated with a project.
This replaces individual, stage-specific tables.
"""

from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base

class PipelineResult(Base):
    """
    Unified database table storing JSON state representing a pipeline stage's output.

    Attributes
    ----------
    project_id : str
        FK referencing the project. Part of the composite primary key.
    stage : str
        The name of the pipeline stage (e.g. 'geometry', 'loads', 'analysis', 'design', 'drawings').
        Part of the composite primary key.
    payload : str
        JSON-serialized dictionary of the stage output.
    updated_at : datetime
        UTC timestamp of the last update to this stage result.
    project : Project
        Relationship reference back to the owning Project.
    """
    __tablename__ = "pipeline_results"

    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("projects.project_id", ondelete="CASCADE"),
        primary_key=True,
        index=True
    )
    stage: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
        index=True
    )
    payload: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationship back to Project (resolved lazily or via join)
    project: Mapped["Project"] = relationship(  # type: ignore[name-defined] # noqa: F821
        "Project",
        back_populates="pipeline_results"
    )

    def __repr__(self) -> str:
        return f"<PipelineResult project_id={self.project_id!r} stage={self.stage!r}>"

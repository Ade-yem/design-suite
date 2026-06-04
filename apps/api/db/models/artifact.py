"""
db/models/artifact.py
====================
SQLAlchemy ORM model for Artifacts (immutable snapshot records).

An Artifact represents a frozen output (geometry, loads, design, drawings) at a
specific gate. Once created, artifacts are read-only. Artifacts form the audit trail
for the project, showing what the engineer approved and when.

The artifact content (geometry JSON, diagram SVG, PDF, etc.) is stored as a
blob — either inline as a Text column or as a reference to external storage.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UUID, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base

if TYPE_CHECKING:
    from db.models.project import Project
    from db.models.user import User


class ArtifactStage(PyEnum):
    """Stage at which the artifact was created."""

    PARSING = "parsing"
    VERIFICATION = "verification"
    LOADING = "loading"
    ANALYSIS = "analysis"
    DESIGN = "design"
    DRAWING = "drawing"


class Artifact(Base):
    """
    Immutable snapshot of a stage output, frozen at gate approval.

    Attributes
    ----------
    artifact_id : str
        UUID primary key, prefixed with "ART-".
    project_id : str
        FK → projects.project_id.
    stage : ArtifactStage
        Which stage this artifact represents (verification, analysis, etc.).
    status : str
        Current status ("signed_off", "in_review", "pending").
        Most artifacts are "signed_off" immediately upon creation.
    content : str | None
        The actual snapshot data: parsed geometry JSON, load diagram SVG, etc.
        Stored as a Text column; serialized from dict to JSON string.
    preview_url : str | None
        Optional URL to a rendered preview (geometry diagram, load diagram, etc.).
        Can be a local blob reference or S3 URL.
    created_at : datetime
        UTC timestamp when the snapshot was created.
    author_id : uuid.UUID | None
        FK → users.id (engineer who approved the gate).
    signature : str | None
        Optional cryptographic signature for audit trail.
        Reserved for future: signing gate approvals for legal compliance.
    """

    __tablename__ = "artifacts"

    artifact_id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: f"ART-{uuid.uuid4().hex[:12].upper()}"
    )
    project_id: Mapped[str] = mapped_column(
        String, ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage: Mapped[ArtifactStage] = mapped_column(Enum(ArtifactStage), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="signed_off")
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preview_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    author_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    signature: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="artifacts")
    author: Mapped[Optional["User"]] = relationship("User")

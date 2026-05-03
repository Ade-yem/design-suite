"""
db/models/organisation.py
=========================
SQLAlchemy ORM model for Organisations (top-level tenancy boundary).

Every User and every Project belongs to exactly one Organisation.
This enforces data isolation at the application layer — all store queries
are automatically scoped to the requesting user's organisation_id.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Organisation(Base):
    """
    Represents a tenant organisation.

    Attributes
    ----------
    id : str
        UUID primary key (text form for portability).
    name : str
        Display name of the organisation (e.g. company name).
    slug : str
        URL-safe unique identifier (e.g. "acme-engineering").
    created_at : datetime
        UTC timestamp when the organisation was created.
    users : list[User]
        All users belonging to this organisation (back-populated).
    projects : list[Project]
        All projects owned by this organisation (back-populated).
    """

    __tablename__ = "organisations"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    users: Mapped[list] = relationship("User", back_populates="organisation")
    projects: Mapped[list] = relationship("Project", back_populates="organisation")

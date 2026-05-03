"""
db/models/user.py
=================
SQLAlchemy ORM model for Users, extending the fastapi-users base table.

fastapi-users provides ``SQLAlchemyBaseUserTableUUID`` which adds:
  - id (UUID primary key)
  - email (unique, indexed)
  - hashed_password
  - is_active, is_superuser, is_verified

We extend it with:
  - organisation_id  (multi-tenancy FK)
  - role             (engineer | admin | viewer)
  - full_name        (display name)
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base
from db.models.organisation import Organisation
from fastapi_users.db import SQLAlchemyBaseUserTableUUID


class User(SQLAlchemyBaseUserTableUUID, Base):
    """
    Application user model.

    Inherits from SQLAlchemyBaseUserTableUUID (fastapi-users):
      - id               : UUID PK (auto-generated)
      - email            : str (unique, indexed)
      - hashed_password  : str
      - is_active        : bool  (default True)
      - is_superuser     : bool  (default False)
      - is_verified      : bool  (default False)

    Additional columns
    ------------------
    full_name : str
        User's display name.
    role : str
        Structural IDE role. One of ``engineer`` | ``admin`` | ``viewer``.
    organisation_id : str | None
        FK → organisations.id.  None only for superusers with no org context.
    organisation : Organisation
        Back-populated relationship to the parent Organisation.
    projects : list[Project]
        Projects created by this user.
    """

    __tablename__ = "users"

    full_name: Mapped[str] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="engineer")
    organisation_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("organisations.id"), nullable=True
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    organisation: Mapped["Organisation"] = relationship(  # noqa: F821
        "Organisation", back_populates="users"
    )
    projects: Mapped[list] = relationship("Project", back_populates="created_by_user")

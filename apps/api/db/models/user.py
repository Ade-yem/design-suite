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
  - is_2fa_enabled   (whether email 2FA is enabled)
  - two_factor_code  (active 6-digit OTP code)
  - two_factor_expires_at (timestamp when OTP code expires)
  - oauth_accounts   (linked social identities)
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from fastapi_users.db import SQLAlchemyBaseUserTableUUID

from db.base import Base

if TYPE_CHECKING:
    from db.models.organisation import Organisation
    from db.models.oauth import OAuthAccount


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
    full_name : str | None
        User's display name.
    role : str
        Structural IDE role. One of ``engineer`` | ``admin`` | ``viewer``.
    organisation_id : str | None
        FK → organisations.id. None only for superusers with no org context.
    is_2fa_enabled : bool
        Whether the user has enabled two-factor authentication via email.
    two_factor_code : str | None
        Active 6-digit verification code used for logging in.
    two_factor_expires_at : datetime | None
        Expiry time for the active 2FA code.
    organisation : Organisation
        Back-populated relationship to the parent Organisation.
    projects : list[Project]
        Projects created by this user.
    oauth_accounts : list[OAuthAccount]
        All linked social login accounts (e.g. Google).
    """

    __tablename__ = "users"

    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    image: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="engineer")
    organisation_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("organisations.id"), nullable=True, index=True
    )

    # ── Two-Factor Authentication (2FA) ───────────────────────────────────────
    is_2fa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    two_factor_code: Mapped[Optional[str]] = mapped_column(String(6), nullable=True)
    two_factor_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    organisation: Mapped[Optional["Organisation"]] = relationship(
        "Organisation", back_populates="users"
    )
    projects: Mapped[list] = relationship("Project", back_populates="created_by_user")
    
    # ── Social Accounts ───────────────────────────────────────────────────────
    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(
        "OAuthAccount",
        lazy="joined",
        back_populates="user",
        cascade="all, delete-orphan",
    )

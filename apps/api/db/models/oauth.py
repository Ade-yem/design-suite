"""
db/models/oauth.py
==================
SQLAlchemy ORM model representing linked social OAuth accounts (e.g. Google).

Subclasses ``SQLAlchemyBaseOAuthAccountTableUUID`` from fastapi-users to store
tokens and user linkages. Overrides the default foreign key to link specifically
to our custom ``users`` table.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from fastapi_users.db import SQLAlchemyBaseOAuthAccountTableUUID

from db.base import Base

if TYPE_CHECKING:
    from db.models.user import User


class OAuthAccount(SQLAlchemyBaseOAuthAccountTableUUID, Base):
    """
    Linked social OAuth account record.

    Stores OAuth access/refresh tokens, expiry times, and unique account
    identifiers retrieved from third-party social providers like Google.

    Attributes
    ----------
    id : uuid.UUID
        Primary key of the linked account record.
    user_id : uuid.UUID
        Foreign key referencing the parent User in the ``users`` table.
    user : User
        Relationship back-populating to the linked User model.
    """

    __tablename__ = "oauth_accounts"

    # Explicitly override the user_id foreign key to point to "users.id" instead of default "user.id"
    # user_id: Mapped[uuid.UUID] = mapped_column(
    #     UUID(as_uuid=True),
    #     ForeignKey("users.id", ondelete="CASCADE"),
    #     nullable=False,
    # )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship(
        "User",
        back_populates="oauth_accounts",
    )

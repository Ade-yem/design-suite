"""
auth/schemas.py
===============
Pydantic schemas for fastapi-users user creation, reading, and updates.

These schemas are used by the ``/auth`` router endpoints provided by
fastapi-users and by any endpoint that returns user data.

Classes
-------
UserRead
    Response schema for user data. Includes org/role fields.
UserCreate
    Request body for registration. Requires email + password.
UserUpdate
    Partial update schema for PATCH /users/me.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi_users import schemas
from pydantic import Field


class UserRead(schemas.BaseUser[uuid.UUID]):
    """
    User response schema returned by GET /users/me and similar endpoints.

    Inherits from BaseUser (provides id, email, is_active, is_superuser,
    is_verified). Extends with application-specific fields.

    Attributes
    ----------
    full_name : str | None
        User's display name.
    role : str
        Structural IDE role: ``engineer`` | ``admin`` | ``viewer``.
    organisation_id : str | None
        UUID string of the user's organisation.
    """

    full_name: Optional[str] = Field(None, description="Display name.")
    role: str = Field("engineer", description="IDE role.")
    organisation_id: Optional[str] = Field(None, description="Organisation UUID.")


class UserCreate(schemas.BaseUserCreate):
    """
    Request body for POST /auth/register.

    Inherits email + password from BaseUserCreate.

    Attributes
    ----------
    full_name : str | None
        Optional display name set at registration.
    organisation_id : str | None
        Pre-assigned organisation UUID (e.g. from an invite link).
    """

    full_name: Optional[str] = Field(None, description="Display name.")
    organisation_id: Optional[str] = Field(None, description="Org UUID from invite.")


class UserUpdate(schemas.BaseUserUpdate):
    """
    Request body for PATCH /users/me.

    All fields are optional. Inherits password from BaseUserUpdate.

    Attributes
    ----------
    full_name : str | None
        Updated display name.
    role : str | None
        Updated role (admin-only change).
    """

    full_name: Optional[str] = None
    role: Optional[str] = None

"""
db/models/__init__.py
=====================
Collects all ORM models so that Alembic / SQLAlchemy metadata can
discover them from a single import.

Usage (Alembic env.py)
----------------------
    import db.models  # noqa — ensures all tables are registered
    from db.base import Base
    target_metadata = Base.metadata
"""

from db.models.organisation import Organisation  # noqa: F401
from db.models.user import User                  # noqa: F401
from db.models.project import (                  # noqa: F401
    Project,
    ProjectMember,
    ProjectLoad,
    ProjectGeometry,
)

__all__ = [
    "Organisation",
    "User",
    "Project",
    "ProjectMember",
    "ProjectLoad",
    "ProjectGeometry",
]

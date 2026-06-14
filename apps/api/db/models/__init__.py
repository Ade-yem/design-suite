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

from db.models.organisation import Organisation
from db.models.user import User
from db.models.oauth import OAuthAccount
from db.models.project import (
    Project,
    ProjectMember,
)
from db.models.pipeline_results import PipelineResult
from db.models.artifact import Artifact, ArtifactStage

__all__ = [
    "Organisation",
    "User",
    "OAuthAccount",
    "Project",
    "ProjectMember",
    "PipelineResult",
    "Artifact",
    "ArtifactStage",
]

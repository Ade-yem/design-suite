"""Baseline full schema.

Establishes the complete database schema as the first migration in the chain so
production deploys are migration-managed (``alembic upgrade head``) instead of
relying on ``Base.metadata.create_all()`` at startup.

The schema is materialised directly from the SQLAlchemy ORM metadata
(``db.models``) — the single source of truth — so it always matches the models
at the time of this revision:

    organisations, users, oauth_accounts, projects, project_members,
    pipeline_results, artifacts

``create_all`` / ``drop_all`` are idempotent at the table level (``checkfirst``),
so this is safe to run against an empty database.  The follow-up revision
``0001_add_project_storeys`` guards on column existence, so running the chain on
a database whose ``projects`` table already carries those columns is a no-op.

Revision ID: 0000_baseline_schema
Revises:
Create Date: 2026-06-17
"""
from __future__ import annotations

from alembic import op

import db.models  # noqa: F401 — ensures all ORM tables register on Base.metadata
from db.base import Base

# revision identifiers, used by Alembic.
revision = "0000_baseline_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, checkfirst=True)

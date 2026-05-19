"""make organisation_id nullable on projects

Revision ID: a3f91b2e4d07
Revises: 8577cf0d5c54
Create Date: 2026-05-19 12:00:00.000000

Allows projects to be created without an organisation context so that the
in-memory project store can persist rows to PostgreSQL without requiring
multi-tenant auth to be fully wired up first.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3f91b2e4d07'
down_revision: Union[str, Sequence[str], None] = '8577cf0d5c54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('projects', 'organisation_id',
                    existing_type=sa.String(),
                    nullable=True)


def downgrade() -> None:
    op.alter_column('projects', 'organisation_id',
                    existing_type=sa.String(),
                    nullable=False)

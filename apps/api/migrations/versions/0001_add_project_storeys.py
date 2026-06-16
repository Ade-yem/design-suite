"""Add num_storeys / storey_height_m to projects.

Building height is collected at upload and drives multi-storey extrapolation
(before Gate-1) and downstream stair geometry. Previously these lived only in
the in-memory LangGraph ``project_parameters`` and were never persisted.

Note: this is the first Alembic revision in the repository; the ``projects``
table is otherwise created from the SQLAlchemy models. The migration guards on
column existence so it is safe to run against a schema that already has (or
lacks) the table/columns.

Revision ID: 0001_add_project_storeys
Revises:
Create Date: 2026-06-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_add_project_storeys"
down_revision = None
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return True  # table absent — created elsewhere with the columns present
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    if not _has_column("projects", "num_storeys"):
        op.add_column(
            "projects",
            sa.Column("num_storeys", sa.Integer(), nullable=False, server_default="1"),
        )
    if not _has_column("projects", "storey_height_m"):
        op.add_column(
            "projects",
            sa.Column("storey_height_m", sa.Float(), nullable=False, server_default="3.0"),
        )


def downgrade() -> None:
    op.drop_column("projects", "storey_height_m")
    op.drop_column("projects", "num_storeys")

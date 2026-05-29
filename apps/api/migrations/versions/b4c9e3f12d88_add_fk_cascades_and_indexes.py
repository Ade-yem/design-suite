"""add FK cascades and indexes

Revision ID: b4c9e3f12d88
Revises: a3f91b2e4d07
Create Date: 2026-05-28 00:00:00.000000

Adds database-level CASCADE DELETE on all project-scoped foreign keys
so that deleting a Project row automatically removes all child rows
(members, loads, geometry, analysis, design, drawings).

Also adds missing btree indexes on high-cardinality FK columns used in
filter queries:
  - projects.organisation_id
  - project_members.project_id
  - users.organisation_id
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b4c9e3f12d88'
down_revision: Union[str, Sequence[str], None] = 'a3f91b2e4d07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _fk_name(table: str, col: str) -> str:
    return f"{table}_{col}_fkey"


def upgrade() -> None:
    # ── project_members: add CASCADE + index ─────────────────────────────────
    op.drop_constraint(_fk_name("project_members", "project_id"), "project_members", type_="foreignkey")
    op.create_foreign_key(
        _fk_name("project_members", "project_id"),
        "project_members", "projects",
        ["project_id"], ["project_id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_project_members_project_id", "project_members", ["project_id"])

    # ── project_loads: add CASCADE ────────────────────────────────────────────
    op.drop_constraint(_fk_name("project_loads", "project_id"), "project_loads", type_="foreignkey")
    op.create_foreign_key(
        _fk_name("project_loads", "project_id"),
        "project_loads", "projects",
        ["project_id"], ["project_id"],
        ondelete="CASCADE",
    )

    # ── project_geometry: add CASCADE ────────────────────────────────────────
    op.drop_constraint(_fk_name("project_geometry", "project_id"), "project_geometry", type_="foreignkey")
    op.create_foreign_key(
        _fk_name("project_geometry", "project_id"),
        "project_geometry", "projects",
        ["project_id"], ["project_id"],
        ondelete="CASCADE",
    )

    # ── project_analysis: add CASCADE ────────────────────────────────────────
    op.drop_constraint(_fk_name("project_analysis", "project_id"), "project_analysis", type_="foreignkey")
    op.create_foreign_key(
        _fk_name("project_analysis", "project_id"),
        "project_analysis", "projects",
        ["project_id"], ["project_id"],
        ondelete="CASCADE",
    )

    # ── project_design: add CASCADE ──────────────────────────────────────────
    op.drop_constraint(_fk_name("project_design", "project_id"), "project_design", type_="foreignkey")
    op.create_foreign_key(
        _fk_name("project_design", "project_id"),
        "project_design", "projects",
        ["project_id"], ["project_id"],
        ondelete="CASCADE",
    )

    # ── project_drawings: add CASCADE ────────────────────────────────────────
    op.drop_constraint(_fk_name("project_drawings", "project_id"), "project_drawings", type_="foreignkey")
    op.create_foreign_key(
        _fk_name("project_drawings", "project_id"),
        "project_drawings", "projects",
        ["project_id"], ["project_id"],
        ondelete="CASCADE",
    )

    # ── indexes ───────────────────────────────────────────────────────────────
    op.create_index("ix_projects_organisation_id", "projects", ["organisation_id"])
    op.create_index("ix_users_organisation_id", "users", ["organisation_id"])


def downgrade() -> None:
    op.drop_index("ix_users_organisation_id", table_name="users")
    op.drop_index("ix_projects_organisation_id", table_name="projects")
    op.drop_index("ix_project_members_project_id", table_name="project_members")

    for table in ("project_drawings", "project_design", "project_analysis",
                  "project_geometry", "project_loads", "project_members"):
        op.drop_constraint(_fk_name(table, "project_id"), table, type_="foreignkey")
        op.create_foreign_key(
            _fk_name(table, "project_id"),
            table, "projects",
            ["project_id"], ["project_id"],
        )

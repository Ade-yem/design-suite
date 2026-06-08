"""merge heads

Revision ID: 17a2ed5063f7
Revises: 2cd76e2f2f83, e718387e4c4d
Create Date: 2026-06-08 11:03:46.362270

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '17a2ed5063f7'
down_revision: Union[str, Sequence[str], None] = ('2cd76e2f2f83', 'e718387e4c4d')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

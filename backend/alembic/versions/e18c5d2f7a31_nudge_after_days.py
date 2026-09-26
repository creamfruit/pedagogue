"""practice nudge interval

Revision ID: e18c5d2f7a31
Revises: d17b3c9a4e10
Create Date: 2026-09-27 00:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e18c5d2f7a31"
down_revision: Union[str, None] = "d17b3c9a4e10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("nudge_after_days", sa.SmallInteger(), server_default="3", nullable=False))


def downgrade() -> None:
    op.drop_column("users", "nudge_after_days")

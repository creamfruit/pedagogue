"""tastes step completion

Revision ID: b31e4c7d9a02
Revises: a23d6e8f1b52
Create Date: 2026-09-27 19:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b31e4c7d9a02"
down_revision: Union[str, None] = "a23d6e8f1b52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tastes_completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "tastes_completed_at")

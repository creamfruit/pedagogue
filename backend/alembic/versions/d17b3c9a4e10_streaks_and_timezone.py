"""streaks: user timezone and streak bonus ledger reason

Revision ID: d17b3c9a4e10
Revises: c13a1f0e2b77
Create Date: 2026-09-26 23:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d17b3c9a4e10"
down_revision: Union[str, None] = "c13a1f0e2b77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False))
    op.execute("ALTER TYPE ledger_reason ADD VALUE IF NOT EXISTS 'streak_bonus'")


def downgrade() -> None:
    op.drop_column("users", "timezone")

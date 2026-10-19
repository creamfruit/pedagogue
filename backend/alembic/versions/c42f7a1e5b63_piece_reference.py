"""piece reference source and facts lookup

Revision ID: c42f7a1e5b63
Revises: b31e4c7d9a02
Create Date: 2026-09-28 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c42f7a1e5b63"
down_revision: Union[str, None] = "b31e4c7d9a02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pieces", sa.Column("reference_url", sa.String(length=300), nullable=True))
    op.add_column("pieces", sa.Column("reference_label", sa.String(length=60), nullable=True))
    op.add_column("pieces", sa.Column("facts_checked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("pieces", "facts_checked_at")
    op.drop_column("pieces", "reference_label")
    op.drop_column("pieces", "reference_url")

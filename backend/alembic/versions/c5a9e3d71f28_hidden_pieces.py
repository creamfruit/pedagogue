"""hidden pieces: an admin can take a piece out of the catalogue at once

Revision ID: c5a9e3d71f28
Revises: b8f3d2a67c15
Create Date: 2026-10-22 20:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c5a9e3d71f28"
down_revision: Union[str, None] = "b8f3d2a67c15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pieces", sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("pieces", sa.Column("hidden_reason", sa.String(length=300), nullable=True))
    op.add_column("pieces", sa.Column("hidden_by", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_pieces_hidden_at"), "pieces", ["hidden_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_pieces_hidden_at"), table_name="pieces")
    op.drop_column("pieces", "hidden_by")
    op.drop_column("pieces", "hidden_reason")
    op.drop_column("pieces", "hidden_at")

"""pieces that borrow harvested data from the same work

Revision ID: d6b2f8e41a93
Revises: c5a9e3d71f28
Create Date: 2026-10-22 21:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d6b2f8e41a93"
down_revision: Union[str, None] = "c5a9e3d71f28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pieces", sa.Column("harvest_piece_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_pieces_harvest_piece_id"), "pieces", ["harvest_piece_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_pieces_harvest_piece_id"), table_name="pieces")
    op.drop_column("pieces", "harvest_piece_id")

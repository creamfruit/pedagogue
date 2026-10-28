"""harvested passages: a source marker and the stored score image of each

Revision ID: a4e1c7b52d90
Revises: f2c8a1d93b47
Create Date: 2026-10-22 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a4e1c7b52d90"
down_revision: Union[str, None] = "f2c8a1d93b47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE passage_source ADD VALUE IF NOT EXISTS 'harvest'")
    op.add_column("passages", sa.Column("image_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("passages", "image_key")

"""harvested pieces: the difficulty computed from the score and the calibration it came from

Revision ID: f2c8a1d93b47
Revises: e7b3c9d41a62
Create Date: 2026-10-22 17:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f2c8a1d93b47"
down_revision: Union[str, None] = "e7b3c9d41a62"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("piece_sources", sa.Column("computed_difficulty", sa.Numeric(precision=4, scale=1), nullable=True))
    op.add_column("piece_sources", sa.Column("calibration_version", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("piece_sources", "calibration_version")
    op.drop_column("piece_sources", "computed_difficulty")

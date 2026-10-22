"""guest users: practise before signing up

Revision ID: d8f2b4a61c07
Revises: c5e1a7d39b20
Create Date: 2026-10-22 16:21:40.220871

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd8f2b4a61c07'
down_revision: Union[str, None] = 'c5e1a7d39b20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_guest', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'is_guest')

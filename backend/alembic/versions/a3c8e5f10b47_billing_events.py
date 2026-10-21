"""billing events: Stripe event ids already handled

Revision ID: a3c8e5f10b47
Revises: f7a1c3d8b205
Create Date: 2026-10-21 16:27:36.078218

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3c8e5f10b47'
down_revision: Union[str, None] = 'f7a1c3d8b205'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('billing_events',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('event_type', sa.String(length=80), nullable=False),
    sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_billing_events'))
    )


def downgrade() -> None:
    op.drop_table('billing_events')

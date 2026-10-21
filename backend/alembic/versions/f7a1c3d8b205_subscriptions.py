"""subscriptions: the paid plan behind each user

Revision ID: f7a1c3d8b205
Revises: e64a9b3d2f01
Create Date: 2026-10-21 16:07:37.563012

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f7a1c3d8b205'
down_revision: Union[str, None] = 'e64a9b3d2f01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('subscriptions',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('provider', sa.String(length=20), server_default='stripe', nullable=False),
    sa.Column('stripe_customer_id', sa.String(length=64), nullable=True),
    sa.Column('stripe_subscription_id', sa.String(length=64), nullable=True),
    sa.Column('status', sa.String(length=24), server_default='incomplete', nullable=False),
    sa.Column('billing_interval', sa.String(length=8), nullable=True),
    sa.Column('trial_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancel_at_period_end', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('trial_used', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('last_event_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_subscriptions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_subscriptions')),
    sa.UniqueConstraint('stripe_customer_id', name='uq_subscriptions_stripe_customer_id'),
    sa.UniqueConstraint('stripe_subscription_id', name='uq_subscriptions_stripe_subscription_id'),
    sa.UniqueConstraint('user_id', name='uq_subscriptions_user_id')
    )
    op.create_index(op.f('ix_subscriptions_user_id'), 'subscriptions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_subscriptions_user_id'), table_name='subscriptions')
    op.drop_table('subscriptions')

"""revenuecat: link store subscriptions to Pedagogue users

Revision ID: b94d2e7a6c13
Revises: a3c8e5f10b47
Create Date: 2026-10-22 13:41:08.114522

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b94d2e7a6c13'
down_revision: Union[str, None] = 'a3c8e5f10b47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('subscriptions', sa.Column('revenuecat_customer_id', sa.String(length=80), nullable=True))
    op.add_column('subscriptions', sa.Column('revenuecat_subscription_id', sa.String(length=80), nullable=True))
    op.create_unique_constraint(op.f('uq_subscriptions_revenuecat_customer_id'), 'subscriptions', ['revenuecat_customer_id'])


def downgrade() -> None:
    op.drop_constraint(op.f('uq_subscriptions_revenuecat_customer_id'), 'subscriptions', type_='unique')
    op.drop_column('subscriptions', 'revenuecat_subscription_id')
    op.drop_column('subscriptions', 'revenuecat_customer_id')

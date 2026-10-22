"""missions: a stored daily practice mission per user

Revision ID: c5e1a7d39b20
Revises: d6b2f8e41a93
Create Date: 2026-10-22 15:02:11.402118

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c5e1a7d39b20'
down_revision: Union[str, None] = "d6b2f8e41a93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('missions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('kind', sa.String(length=12), server_default='daily', nullable=False),
    sa.Column('steps', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('progress', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('session_id', sa.Uuid(), nullable=True),
    sa.Column('owns_session', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['session_id'], ['practice_sessions.id'], name=op.f('fk_missions_session_id_practice_sessions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_missions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_missions')),
    sa.UniqueConstraint('user_id', 'day', name='uq_missions_user_id_day')
    )
    op.create_index(op.f('ix_missions_user_id'), 'missions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_missions_user_id'), table_name='missions')
    op.drop_table('missions')

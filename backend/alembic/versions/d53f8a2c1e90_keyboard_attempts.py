"""keyboard attempts, per-bar results and the keyboard practice mode

Revision ID: d53f8a2c1e90
Revises: c42f7a1e5b63
Create Date: 2026-10-19 11:46:51.052353

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd53f8a2c1e90'
down_revision: Union[str, None] = 'c42f7a1e5b63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE practice_mode ADD VALUE IF NOT EXISTS 'keyboard'")
    op.create_table('keyboard_attempts',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('repertoire_entry_id', sa.Uuid(), nullable=False),
    sa.Column('passage_id', sa.Integer(), nullable=True),
    sa.Column('session_id', sa.Uuid(), nullable=True),
    sa.Column('mode', sa.String(length=10), nullable=False),
    sa.Column('start_bar', sa.Integer(), nullable=True),
    sa.Column('end_bar', sa.Integer(), nullable=True),
    sa.Column('tempo_bpm', sa.SmallInteger(), nullable=True),
    sa.Column('achieved_tempo_bpm', sa.Numeric(precision=5, scale=1), nullable=True),
    sa.Column('expected', sa.Integer(), server_default='0', nullable=False),
    sa.Column('correct', sa.Integer(), server_default='0', nullable=False),
    sa.Column('wrong', sa.Integer(), server_default='0', nullable=False),
    sa.Column('missing', sa.Integer(), server_default='0', nullable=False),
    sa.Column('played', sa.Integer(), server_default='0', nullable=False),
    sa.Column('accuracy', sa.Numeric(precision=5, scale=4), nullable=True),
    sa.Column('timing', sa.Numeric(precision=4, scale=1), nullable=True),
    sa.Column('evenness', sa.Numeric(precision=4, scale=1), nullable=True),
    sa.Column('overall', sa.Numeric(precision=4, scale=1), server_default='0', nullable=False),
    sa.Column('clean', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('late', sa.Integer(), server_default='0', nullable=False),
    sa.Column('early', sa.Integer(), server_default='0', nullable=False),
    sa.Column('duration_sec', sa.Numeric(precision=7, scale=1), server_default='0', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("mode IN ('scored', 'wait', 'free')", name=op.f('ck_keyboard_attempts_mode_known')),
    sa.CheckConstraint('start_bar IS NULL OR end_bar IS NULL OR end_bar >= start_bar', name=op.f('ck_keyboard_attempts_bar_order')),
    sa.ForeignKeyConstraint(['passage_id'], ['passages.id'], name=op.f('fk_keyboard_attempts_passage_id_passages'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['repertoire_entry_id'], ['repertoire_entries.id'], name=op.f('fk_keyboard_attempts_repertoire_entry_id_repertoire_entries'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['session_id'], ['practice_sessions.id'], name=op.f('fk_keyboard_attempts_session_id_practice_sessions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_keyboard_attempts_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_keyboard_attempts'))
    )
    op.create_index(op.f('ix_keyboard_attempts_passage_id'), 'keyboard_attempts', ['passage_id'], unique=False)
    op.create_index(op.f('ix_keyboard_attempts_repertoire_entry_id'), 'keyboard_attempts', ['repertoire_entry_id'], unique=False)
    op.create_index(op.f('ix_keyboard_attempts_session_id'), 'keyboard_attempts', ['session_id'], unique=False)
    op.create_index(op.f('ix_keyboard_attempts_user_id'), 'keyboard_attempts', ['user_id'], unique=False)
    op.create_table('keyboard_attempt_bars',
    sa.Column('attempt_id', sa.Uuid(), nullable=False),
    sa.Column('bar', sa.Integer(), nullable=False),
    sa.Column('expected', sa.Integer(), server_default='0', nullable=False),
    sa.Column('correct', sa.Integer(), server_default='0', nullable=False),
    sa.Column('wrong', sa.Integer(), server_default='0', nullable=False),
    sa.Column('missing', sa.Integer(), server_default='0', nullable=False),
    sa.Column('accuracy', sa.Numeric(precision=5, scale=4), nullable=True),
    sa.Column('tempo_bpm', sa.Numeric(precision=5, scale=1), nullable=True),
    sa.Column('timing_error_ms', sa.Numeric(precision=6, scale=1), nullable=True),
    sa.Column('timing_score', sa.Numeric(precision=4, scale=1), nullable=True),
    sa.Column('late', sa.Integer(), server_default='0', nullable=False),
    sa.Column('early', sa.Integer(), server_default='0', nullable=False),
    sa.ForeignKeyConstraint(['attempt_id'], ['keyboard_attempts.id'], name=op.f('fk_keyboard_attempt_bars_attempt_id_keyboard_attempts'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('attempt_id', 'bar', name=op.f('pk_keyboard_attempt_bars'))
    )


def downgrade() -> None:
    op.drop_table('keyboard_attempt_bars')
    op.drop_index(op.f('ix_keyboard_attempts_user_id'), table_name='keyboard_attempts')
    op.drop_index(op.f('ix_keyboard_attempts_session_id'), table_name='keyboard_attempts')
    op.drop_index(op.f('ix_keyboard_attempts_repertoire_entry_id'), table_name='keyboard_attempts')
    op.drop_index(op.f('ix_keyboard_attempts_passage_id'), table_name='keyboard_attempts')
    op.drop_table('keyboard_attempts')

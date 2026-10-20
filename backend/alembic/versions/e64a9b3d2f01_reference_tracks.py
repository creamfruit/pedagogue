"""reference tracks: a MIDI or MusicXML file attached to a piece

Revision ID: e64a9b3d2f01
Revises: d53f8a2c1e90
Create Date: 2026-10-20 09:10:07.535458

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e64a9b3d2f01'
down_revision: Union[str, None] = 'd53f8a2c1e90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('reference_tracks',
    sa.Column('repertoire_entry_id', sa.Uuid(), nullable=False),
    sa.Column('source_kind', sa.String(length=10), nullable=False),
    sa.Column('filename', sa.String(length=200), nullable=False),
    sa.Column('storage_key', sa.Text(), nullable=False),
    sa.Column('quarter_bpm', sa.Numeric(precision=5, scale=1), nullable=True),
    sa.Column('note_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('bar_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['repertoire_entry_id'], ['repertoire_entries.id'], name=op.f('fk_reference_tracks_repertoire_entry_id_repertoire_entries'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reference_tracks')),
    sa.UniqueConstraint('repertoire_entry_id', name='uq_reference_tracks_repertoire_entry_id')
    )
    op.create_index(op.f('ix_reference_tracks_repertoire_entry_id'), 'reference_tracks', ['repertoire_entry_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_reference_tracks_repertoire_entry_id'), table_name='reference_tracks')
    op.drop_table('reference_tracks')

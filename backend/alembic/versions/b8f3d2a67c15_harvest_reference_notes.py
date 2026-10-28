"""reference notes for harvested pieces, in the form the keyboard scoring engine reads

Revision ID: b8f3d2a67c15
Revises: a4e1c7b52d90
Create Date: 2026-10-22 19:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b8f3d2a67c15"
down_revision: Union[str, None] = "a4e1c7b52d90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "piece_reference_notes",
        sa.Column("piece_id", sa.Integer(), nullable=False),
        sa.Column("quarter_bpm", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("note_count", sa.Integer(), nullable=False),
        sa.Column("bar_count", sa.Integer(), nullable=False),
        sa.Column("notes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("bar_starts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("bar_lengths", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["piece_id"], ["pieces.id"], name=op.f("fk_piece_reference_notes_piece_id_pieces"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("piece_id", name=op.f("pk_piece_reference_notes")),
    )
    op.add_column("piece_sources", sa.Column("scoring_ready", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("piece_sources", sa.Column("scoring_issues", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("piece_sources", "scoring_issues")
    op.drop_column("piece_sources", "scoring_ready")
    op.drop_table("piece_reference_notes")

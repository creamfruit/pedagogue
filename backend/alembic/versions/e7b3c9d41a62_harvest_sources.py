"""harvested pieces: where each came from, its licence, and the features measured from the score

Revision ID: e7b3c9d41a62
Revises: b94d2e7a6c13
Create Date: 2026-10-22 16:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e7b3c9d41a62"
down_revision: Union[str, None] = "b94d2e7a6c13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "piece_sources",
        sa.Column("piece_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.String(length=120), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("licence_code", sa.String(length=20), nullable=False),
        sa.Column("licence_name", sa.String(length=60), nullable=False),
        sa.Column("licence_url", sa.String(length=200), nullable=False),
        sa.Column("composer_name", sa.String(length=160), nullable=False),
        sa.Column("composer_qid", sa.String(length=20), nullable=True),
        sa.Column("composer_died_on", sa.Date(), nullable=True),
        sa.Column("attribution", sa.Text(), nullable=True),
        sa.Column("original_title", sa.String(length=300), nullable=True),
        sa.Column("file_urls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("feature_version", sa.SmallInteger(), nullable=True),
        sa.Column("harvested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["piece_id"], ["pieces.id"], name=op.f("fk_piece_sources_piece_id_pieces"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("piece_id", name=op.f("pk_piece_sources")),
        sa.UniqueConstraint("source", "source_id", name="uq_piece_sources_source_id"),
    )
    op.create_index(op.f("ix_piece_sources_source"), "piece_sources", ["source"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_piece_sources_source"), table_name="piece_sources")
    op.drop_table("piece_sources")

"""meteor shower events

Revision ID: a23d6e8f1b52
Revises: f20a9b1c3d44
Create Date: 2026-09-27 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a23d6e8f1b52"
down_revision: Union[str, None] = "f20a9b1c3d44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "meteor_showers",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("catch_xp", sa.Integer(), server_default="40", nullable=False),
        sa.Column("catch_gold", sa.Integer(), server_default="25", nullable=False),
        sa.Column("learn_multiplier", sa.Numeric(precision=3, scale=2), server_default="1.50", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_meteor_showers_window_order")),
        sa.CheckConstraint("learn_multiplier >= 1", name=op.f("ck_meteor_showers_learn_multiplier_floor")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_meteor_showers_created_by_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meteor_showers")),
    )
    op.create_index(op.f("ix_meteor_showers_starts_at"), "meteor_showers", ["starts_at"], unique=False)
    op.create_index(op.f("ix_meteor_showers_ends_at"), "meteor_showers", ["ends_at"], unique=False)
    op.create_table(
        "meteor_shower_pieces",
        sa.Column("shower_id", sa.Integer(), nullable=False),
        sa.Column("piece_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.SmallInteger(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["piece_id"], ["pieces.id"], name=op.f("fk_meteor_shower_pieces_piece_id_pieces"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shower_id"], ["meteor_showers.id"], name=op.f("fk_meteor_shower_pieces_shower_id_meteor_showers"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("shower_id", "piece_id", name=op.f("pk_meteor_shower_pieces")),
    )
    op.add_column("repertoire_entries", sa.Column("meteor_shower_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_repertoire_entries_meteor_shower_id"), "repertoire_entries", ["meteor_shower_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_repertoire_entries_meteor_shower_id_meteor_showers"),
        "repertoire_entries",
        "meteor_showers",
        ["meteor_shower_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute("ALTER TYPE ledger_reason ADD VALUE IF NOT EXISTS 'meteor_catch'")


def downgrade() -> None:
    op.drop_constraint(op.f("fk_repertoire_entries_meteor_shower_id_meteor_showers"), "repertoire_entries", type_="foreignkey")
    op.drop_index(op.f("ix_repertoire_entries_meteor_shower_id"), table_name="repertoire_entries")
    op.drop_column("repertoire_entries", "meteor_shower_id")
    op.drop_table("meteor_shower_pieces")
    op.drop_index(op.f("ix_meteor_showers_ends_at"), table_name="meteor_showers")
    op.drop_index(op.f("ix_meteor_showers_starts_at"), table_name="meteor_showers")
    op.drop_table("meteor_showers")

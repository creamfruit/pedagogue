"""leaderboards, daily sight-reading roulette, leaderboard opt-in

Revision ID: f20a9b1c3d44
Revises: e18c5d2f7a31
Create Date: 2026-09-27 02:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f20a9b1c3d44"
down_revision: Union[str, None] = "e18c5d2f7a31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("leaderboard_opt_in", sa.Boolean(), server_default="false", nullable=False))
    op.create_table(
        "leaderboard_entries",
        sa.Column("board", sa.String(length=60), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_leaderboard_entries_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("board", "user_id", name=op.f("pk_leaderboard_entries")),
    )
    op.create_index(op.f("ix_leaderboard_entries_user_id"), "leaderboard_entries", ["user_id"], unique=False)
    op.create_table(
        "daily_snippets",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("difficulty", sa.Numeric(precision=3, scale=1), nullable=False),
        sa.Column("notation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("quiz", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_daily_snippets")),
    )
    op.create_table(
        "roulette_attempts",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["day"], ["daily_snippets.day"], name=op.f("fk_roulette_attempts_day_daily_snippets"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_roulette_attempts_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roulette_attempts")),
        sa.UniqueConstraint("day", "user_id", name="uq_roulette_attempts_day_user"),
    )
    op.create_index(op.f("ix_roulette_attempts_day"), "roulette_attempts", ["day"], unique=False)
    op.create_index(op.f("ix_roulette_attempts_user_id"), "roulette_attempts", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("roulette_attempts")
    op.drop_table("daily_snippets")
    op.drop_index(op.f("ix_leaderboard_entries_user_id"), table_name="leaderboard_entries")
    op.drop_table("leaderboard_entries")
    op.drop_column("users", "leaderboard_opt_in")

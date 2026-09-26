"""ai generations ledger

Revision ID: c13a1f0e2b77
Revises: a77858f33c61
Create Date: 2026-09-26 20:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c13a1f0e2b77"
down_revision: Union[str, None] = "a77858f33c61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_generations",
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("subject_key", sa.String(length=120), nullable=False),
        sa.Column("status", sa.Enum("running", "done", "failed", name="generation_status"), nullable=False),
        sa.Column("model", sa.String(length=60), nullable=True),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_generations")),
        sa.UniqueConstraint("purpose", "subject_key", name="uq_ai_generations_subject"),
    )


def downgrade() -> None:
    op.drop_table("ai_generations")
    sa.Enum(name="generation_status").drop(op.get_bind(), checkfirst=True)

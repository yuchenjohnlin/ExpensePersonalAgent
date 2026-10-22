"""platform: the job table

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_job",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.Text(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name=op.f("ck_platform_job_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_job")),
    )
    op.create_index("ix_platform_job_ready", "platform_job", ["run_after", "id"],
                    postgresql_where=sa.text("status = 'queued'"))


def downgrade() -> None:
    op.drop_table("platform_job")

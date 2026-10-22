"""platform: job priority, so quick follow-up steps run before readings queued earlier

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("platform_job", sa.Column("priority", sa.Integer(), nullable=False, server_default="0"))
    op.alter_column("platform_job", "priority", server_default=None)
    op.drop_index("ix_platform_job_ready", table_name="platform_job")
    op.create_index("ix_platform_job_ready", "platform_job", ["priority", "id"],
                    postgresql_where=sa.text("status = 'queued'"))


def downgrade() -> None:
    op.drop_index("ix_platform_job_ready", table_name="platform_job")
    op.create_index("ix_platform_job_ready", "platform_job", ["run_after", "id"],
                    postgresql_where=sa.text("status = 'queued'"))
    op.drop_column("platform_job", "priority")

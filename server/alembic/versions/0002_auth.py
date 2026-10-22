"""auth: users and sessions

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_user",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(150), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_user")),
        sa.UniqueConstraint("username", name=op.f("uq_auth_user_username")),
    )
    op.create_table(
        "auth_session",
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("password_tag", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["auth_user.id"], name=op.f("fk_auth_session_user_id_auth_user"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash", name=op.f("pk_auth_session")),
    )
    op.create_index("ix_auth_session_user_id", "auth_session", ["user_id"])


def downgrade() -> None:
    op.drop_table("auth_session")
    op.drop_table("auth_user")

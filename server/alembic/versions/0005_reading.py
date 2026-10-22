"""reading: readings and the photos each reads

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

STAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "reading_reading",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("params", postgresql.JSONB(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("raw_response", postgresql.JSONB(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("then_kind", sa.Text(), nullable=False),
        sa.Column("then_payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", STAMP, nullable=False),
        sa.Column("started_at", STAMP, nullable=True),
        sa.Column("completed_at", STAMP, nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')",
                           name=op.f("ck_reading_reading_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reading_reading")),
    )
    op.create_table(
        "reading_photo",
        sa.Column("reading_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("photo_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["reading_id"], ["reading_reading.id"],
                                name=op.f("fk_reading_photo_reading_id_reading_reading"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["photo_id"], ["photos_photo.id"], name=op.f("fk_reading_photo_photo_id_photos_photo"),
                                ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("reading_id", "position", name=op.f("pk_reading_photo")),
    )


def downgrade() -> None:
    op.drop_table("reading_photo")
    op.drop_table("reading_reading")

"""photos: uploads and photos

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "photos_upload",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("channel IN ('receipt_page')", name=op.f("ck_photos_upload_channel")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_photos_upload")),
    )
    op.create_table(
        "photos_photo",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("upload_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.Uuid(), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(32), nullable=False),
        sa.Column("extension", sa.String(5), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["upload_id"], ["photos_upload.id"], name=op.f("fk_photos_photo_upload_id_photos_upload"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_photos_photo")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_photos_photo_storage_key")),
        sa.UniqueConstraint("upload_id", "position", name="uq_photos_photo_upload_position"),
    )
    op.create_index("ix_photos_photo_owner_sha256", "photos_photo", ["owner_id", "sha256"])


def downgrade() -> None:
    op.drop_table("photos_photo")
    op.drop_table("photos_upload")

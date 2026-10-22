"""receipts: receipts, their photos and readings, postings and posted lines

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

STAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "receipts_receipt",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline", sa.Text(), nullable=False),
        sa.Column("review_reasons", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", STAMP, nullable=False),
        sa.Column("updated_at", STAMP, nullable=False),
        sa.CheckConstraint("pipeline IN ('reading', 'done')", name=op.f("ck_receipts_receipt_pipeline")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_receipts_receipt")),
    )
    op.create_index("ix_receipts_receipt_owner_id", "receipts_receipt", ["owner_id", "id"])
    op.create_table(
        "receipts_receipt_photo",
        sa.Column("receipt_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("photo_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts_receipt.id"],
                                name=op.f("fk_receipts_receipt_photo_receipt_id_receipts_receipt"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["photo_id"], ["photos_photo.id"],
                                name=op.f("fk_receipts_receipt_photo_photo_id_photos_photo"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("receipt_id", "position", name=op.f("pk_receipts_receipt_photo")),
        sa.UniqueConstraint("photo_id", name="uq_receipts_receipt_photo_photo_id"),
    )
    op.create_table(
        "receipts_receipt_reading",
        sa.Column("reading_id", sa.BigInteger(), nullable=False),
        sa.Column("receipt_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", STAMP, nullable=False),
        sa.ForeignKeyConstraint(["reading_id"], ["reading_reading.id"],
                                name=op.f("fk_receipts_receipt_reading_reading_id_reading_reading"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts_receipt.id"],
                                name=op.f("fk_receipts_receipt_reading_receipt_id_receipts_receipt"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("reading_id", name=op.f("pk_receipts_receipt_reading")),
    )
    op.create_index("ix_receipts_receipt_reading_receipt_id", "receipts_receipt_reading", ["receipt_id"])
    op.create_table(
        "receipts_posting",
        sa.Column("receipt_id", sa.BigInteger(), nullable=False),
        sa.Column("expense_id", sa.BigInteger(), nullable=False),
        sa.Column("reading_id", sa.BigInteger(), nullable=True),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("skipped", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", STAMP, nullable=False),
        sa.CheckConstraint("mode IN ('auto', 'manual')", name=op.f("ck_receipts_posting_mode")),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts_receipt.id"],
                                name=op.f("fk_receipts_posting_receipt_id_receipts_receipt"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["expense_id"], ["ledger_expense.id"],
                                name=op.f("fk_receipts_posting_expense_id_ledger_expense"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reading_id"], ["reading_reading.id"],
                                name=op.f("fk_receipts_posting_reading_id_reading_reading"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("receipt_id", name=op.f("pk_receipts_posting")),
    )
    op.create_index("ix_receipts_posting_expense_id", "receipts_posting", ["expense_id"])
    op.create_table(
        "receipts_posted_line",
        sa.Column("line_id", sa.BigInteger(), nullable=False),
        sa.Column("receipt_id", sa.BigInteger(), nullable=False),
        sa.Column("reading_id", sa.BigInteger(), nullable=False),
        sa.Column("item_index", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["line_id"], ["ledger_line.id"],
                                name=op.f("fk_receipts_posted_line_line_id_ledger_line"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts_receipt.id"],
                                name=op.f("fk_receipts_posted_line_receipt_id_receipts_receipt"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reading_id"], ["reading_reading.id"],
                                name=op.f("fk_receipts_posted_line_reading_id_reading_reading"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("line_id", name=op.f("pk_receipts_posted_line")),
    )
    op.create_index("ix_receipts_posted_line_receipt_id", "receipts_posted_line", ["receipt_id"])


def downgrade() -> None:
    for table in ("receipts_posted_line", "receipts_posting", "receipts_receipt_reading", "receipts_receipt_photo",
                  "receipts_receipt"):
        op.drop_table(table)

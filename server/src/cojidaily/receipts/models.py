import uuid
from datetime import datetime

from sqlalchemy import (BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, Integer, Text,
                        UniqueConstraint, Uuid)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..platform.db import Base


class Receipt(Base):
    """One receipt. Whether it is posted is whether a Posting exists (the ledger may delete the
    expense, which takes the posting with it); pipeline says whether a reading is still pending."""
    __tablename__ = "receipts_receipt"
    __table_args__ = (
        CheckConstraint("pipeline IN ('reading', 'done')", name="pipeline"),
        Index("ix_receipts_receipt_owner_id", "owner_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    pipeline: Mapped[str] = mapped_column(Text)
    # Why it was not posted automatically (or was unposted): shown in "needs a look".
    review_reasons: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    photos: Mapped[list["ReceiptPhoto"]] = relationship(order_by="ReceiptPhoto.position", lazy="selectin",
                                                        cascade="all, delete-orphan")
    posting: Mapped["Posting | None"] = relationship(lazy="selectin", viewonly=True)


class ReceiptPhoto(Base):
    __tablename__ = "receipts_receipt_photo"
    __table_args__ = (UniqueConstraint("photo_id", name="uq_receipts_receipt_photo_photo_id"),)

    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts_receipt.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    photo_id: Mapped[int] = mapped_column(ForeignKey("photos_photo.id", ondelete="RESTRICT"))


class ReceiptReading(Base):
    """A reading asked for this receipt; the newest one is the receipt's current reading."""
    __tablename__ = "receipts_receipt_reading"
    __table_args__ = (Index("ix_receipts_receipt_reading_receipt_id", "receipt_id"),)

    reading_id: Mapped[int] = mapped_column(ForeignKey("reading_reading.id", ondelete="RESTRICT"), primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts_receipt.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Posting(Base):
    """The receipt became this expense: automatically from a reading, or by hand."""
    __tablename__ = "receipts_posting"
    __table_args__ = (
        CheckConstraint("mode IN ('auto', 'manual')", name="mode"),
        Index("ix_receipts_posting_expense_id", "expense_id"),
    )

    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts_receipt.id", ondelete="CASCADE"), primary_key=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey("ledger_expense.id", ondelete="CASCADE"))
    reading_id: Mapped[int | None] = mapped_column(ForeignKey("reading_reading.id", ondelete="RESTRICT"))
    mode: Mapped[str] = mapped_column(Text)
    # Read items that did not become lines, and why (a negative deduction, a value a line cannot hold).
    skipped: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PostedLine(Base):
    """This ledger line started as item `item_index` (1-based) of that reading."""
    __tablename__ = "receipts_posted_line"
    __table_args__ = (Index("ix_receipts_posted_line_receipt_id", "receipt_id"),)

    line_id: Mapped[int] = mapped_column(ForeignKey("ledger_line.id", ondelete="CASCADE"), primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts_receipt.id", ondelete="CASCADE"))
    reading_id: Mapped[int] = mapped_column(ForeignKey("reading_reading.id", ondelete="RESTRICT"))
    item_index: Mapped[int] = mapped_column(Integer)

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Identity, Index, Integer,
                        Numeric, String, Text, UniqueConstraint, Uuid, text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..platform.db import Base

MONEY = Numeric(10, 2)
MEASURE = Numeric(16, 6)


class Category(Base):
    """One owner's category. Every account starts with the old app's eight and a system
    "未分類" (system_key 'uncategorized'), which auto-posted expenses get (pm/decisions/auto-post-uncategorized.md)."""
    __tablename__ = "ledger_category"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_ledger_category_owner_name"),
        Index("uq_ledger_category_owner_system_key", "owner_id", "system_key", unique=True,
              postgresql_where=text("system_key IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # auth_user's id, with no foreign key: auth may become an outside identity provider.
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    name: Mapped[str] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(Integer)
    system_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Expense(Base):
    """What was paid, once. amount is the truth for every total; lines are a breakdown that may be partial."""
    __tablename__ = "ledger_expense"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("(tax IS NULL OR tax >= 0) AND tip >= 0 AND receipt_discount >= 0", name="adjustments_nonnegative"),
        CheckConstraint("COALESCE(tax, 0) + tip < amount", name="tax_and_tip_below_amount"),
        Index("ix_ledger_expense_owner_date", "owner_id", "date"),
        Index("ix_ledger_expense_unreviewed", "owner_id", "id", postgresql_where=text("reviewed_at IS NULL")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    title: Mapped[str] = mapped_column(String(120))
    amount: Mapped[Decimal] = mapped_column(MONEY)
    date: Mapped[date] = mapped_column(Date)
    category_id: Mapped[int] = mapped_column(ForeignKey("ledger_category.id", ondelete="RESTRICT"))
    merchant: Mapped[str] = mapped_column(String(120))
    notes: Mapped[str] = mapped_column(String(500))
    # What the receipt prints. tax NULL = not known yet; tip and receipt_discount 0 = none.
    tax: Mapped[Decimal | None] = mapped_column(MONEY)
    tip: Mapped[Decimal] = mapped_column(MONEY)
    receipt_discount: Mapped[Decimal] = mapped_column(MONEY)
    # No item breakdown can be had, as opposed to not entered yet. Only without lines.
    total_only: Mapped[bool] = mapped_column(Boolean)
    # NULL: posted automatically and not looked at yet (pm/decisions/expense-review-status-not-drafts.md).
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    category: Mapped[Category] = relationship(lazy="joined", innerjoin=True)
    lines: Mapped[list["Line"]] = relationship(back_populates="expense", order_by="Line.id",
                                               cascade="all, delete-orphan", passive_deletes=True)


class Line(Base):
    """One thing on the receipt, as printed. Edited in place, so its id stays: later modules
    (receipts' provenance, inventory) point at it."""
    __tablename__ = "ledger_line"
    __table_args__ = (
        CheckConstraint("amount IS NULL OR amount >= 0", name="amount_nonnegative"),
        CheckConstraint("discount = 0 OR (amount IS NOT NULL AND discount > 0 AND discount <= amount)",
                        name="discount_within_amount"),
        CheckConstraint("quantity IS NULL OR quantity >= 0", name="quantity_nonnegative"),
        CheckConstraint("quoted_unit_price IS NULL OR quoted_unit_price >= 0", name="price_nonnegative"),
        CheckConstraint("net_weight IS NULL OR net_weight > 0", name="weight_positive"),
        CheckConstraint("derived_field = '' OR (derived_field = 'quantity' AND quantity IS NOT NULL) "
                        "OR (derived_field = 'quoted_unit_price' AND quoted_unit_price IS NOT NULL) "
                        "OR (derived_field = 'net_weight' AND net_weight IS NOT NULL)", name="derived_value_present"),
        Index("ix_ledger_line_expense_id", "expense_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey("ledger_expense.id", ondelete="CASCADE"))
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal | None] = mapped_column(MEASURE)
    unit: Mapped[str] = mapped_column(String(8))
    # The item's own price before its own discount; NULL while unknown.
    amount: Mapped[Decimal | None] = mapped_column(MONEY)
    discount: Mapped[Decimal] = mapped_column(MONEY)
    quoted_unit_price: Mapped[Decimal | None] = mapped_column(MEASURE)
    price_unit: Mapped[str] = mapped_column(String(8))
    net_weight: Mapped[Decimal | None] = mapped_column(MEASURE)
    weight_unit: Mapped[str] = mapped_column(String(4))
    notes: Mapped[str] = mapped_column(String(500))
    # Which field the server worked out from amount = measure x unit price ('' for none).
    derived_field: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    expense: Mapped[Expense] = relationship(back_populates="lines")

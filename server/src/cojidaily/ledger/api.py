"""What other modules may use from the ledger.

receipts posts a reading as an expense with lines and keeps its own links to the ids returned;
the CLI gives a new account its categories.
"""
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import service
from .lines import check_line as _check_line
from .models import Expense, Line
from .schemas import ExpenseIn as ExpenseHeader  # noqa: F401  (the body of a hand-entered expense)

ensure_categories = service.ensure_categories
uncategorized_category_id = service.uncategorized_id


def check_line(values: dict) -> tuple[dict | None, str]:
    """A line's values (text or None) -> (clean values, "") or (None, why it cannot be a line)."""
    clean, errors = _check_line(values)
    return clean, " ".join(message for messages in errors.values() for message in messages)


def create_expense(db: Session, owner: uuid.UUID, header: dict, lines: list[dict], *,
                   reviewed: bool) -> tuple[int, list[int]]:
    """An expense and its lines in the caller's transaction; (expense id, line ids in order).

    header: title, amount, date, category_id, merchant, notes, tax, tip, receipt_discount (clean);
    lines: clean values from check_line. Raises platform.errors.ApiError (400 with fields) when
    the header breaks a ledger rule, before writing anything."""
    expense = service.create_expense(db, owner, header, reviewed=reviewed)
    return expense.id, [service.add_line(db, owner, expense.id, values).id for values in lines]


def delete_expense(db: Session, owner: uuid.UUID, expense_id: int) -> None:
    service.delete_expense(db, owner, expense_id)


def similar_expense_ids(db: Session, owner: uuid.UUID, day: date, amount: Decimal, merchant: str) -> list[int]:
    return service.similar(db, owner, day, amount, merchant)


@dataclass(frozen=True)
class ExpenseSummary:
    id: int
    title: str
    merchant: str
    date: date
    amount: str
    category: str
    reviewed_at: datetime | None
    line_count: int


def summaries(db: Session, owner: uuid.UUID, expense_ids) -> dict[int, ExpenseSummary]:
    ids = list(expense_ids)
    if not ids:
        return {}
    counts = dict(db.execute(select(Line.expense_id, func.count()).where(Line.expense_id.in_(ids))
                             .group_by(Line.expense_id)).all())
    return {e.id: ExpenseSummary(e.id, e.title, e.merchant, e.date, service.money(e.amount), e.category.name,
                                 e.reviewed_at, counts.get(e.id, 0))
            for e in db.scalars(select(Expense).where(Expense.owner_id == owner, Expense.id.in_(ids)))}

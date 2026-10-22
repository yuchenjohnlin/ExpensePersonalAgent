"""The ledger's endpoints. Every write answers the whole expense with its lines and summary, so the
page can redraw from the answer."""
import re
from calendar import monthrange
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Query, Request

from ..auth.api import Signed
from ..platform import clock
from ..platform.db import Db
from ..platform.errors import ApiError, invalid
from . import service
from .schemas import ExpenseIn, ExpensePatch, LineIn, LinePatch

router = APIRouter(prefix="/api")


@router.get("/categories")
def categories(principal: Signed, db: Db) -> list[dict]:
    return [{"id": c.id, "name": c.name, "system": c.system_key is not None}
            for c in service.categories(db, principal.user_id)]


@router.post("/expenses", status_code=201)
def create_expense(body: ExpenseIn, principal: Signed, db: Db) -> dict:
    """A hand-entered expense: looked at by definition (reviewed)."""
    expense = service.create_expense(db, principal.user_id, body.model_dump(), reviewed=True)
    db.commit()
    return service.expense_with_lines_out(service.expense_with_lines(db, principal.user_id, expense.id))


@router.get("/expenses/unreviewed")
def unreviewed(principal: Signed, db: Db) -> list[dict]:
    """Expenses posted automatically and not looked at yet, newest first."""
    return [service.expense_with_lines_out(expense) for expense in service.unreviewed(db, principal.user_id)]


@router.get("/expenses/{expense_id}")
def expense(expense_id: int, principal: Signed, db: Db) -> dict:
    return service.expense_with_lines_out(service.expense_with_lines(db, principal.user_id, expense_id))


NOT_NULL = ("title", "amount", "date", "category_id", "merchant", "notes", "total_only", "reviewed")


@router.patch("/expenses/{expense_id}")
def change_expense(expense_id: int, body: ExpensePatch, principal: Signed, db: Db) -> dict:
    sent = body.model_fields_set
    if not sent:
        raise ApiError(400, "沒有要修改的欄位。")
    nulls = {name: ["此為必需欄位。"] for name in NOT_NULL if name in sent and getattr(body, name) is None}
    if nulls:
        raise invalid(nulls)
    changes = {name: getattr(body, name) for name in sent}
    for name in ("tip", "receipt_discount"):  # null = none
        if name in changes and changes[name] is None:
            changes[name] = Decimal("0.00")
    service.update_expense(db, principal.user_id, expense_id, changes)
    db.commit()
    return service.expense_with_lines_out(service.expense_with_lines(db, principal.user_id, expense_id))


@router.delete("/expenses/{expense_id}")
def delete_expense(expense_id: int, principal: Signed, db: Db) -> dict:
    service.delete_expense(db, principal.user_id, expense_id)
    db.commit()
    return {"deleted": expense_id}


@router.post("/expenses/{expense_id}/lines", status_code=201)
def add_line(expense_id: int, body: LineIn, principal: Signed, db: Db) -> dict:
    line = service.add_line(db, principal.user_id, expense_id, body.model_dump())
    db.commit()
    return {"line_id": line.id} | service.expense_with_lines_out(
        service.expense_with_lines(db, principal.user_id, expense_id))


@router.patch("/lines/{line_id}")
def change_line(line_id: int, body: LinePatch, principal: Signed, db: Db) -> dict:
    changes = {name: getattr(body, name) for name in body.model_fields_set}
    line = service.update_line(db, principal.user_id, line_id, changes)
    db.commit()
    return service.expense_with_lines_out(service.expense_with_lines(db, principal.user_id, line.expense_id))


@router.delete("/lines/{line_id}")
def delete_line(line_id: int, principal: Signed, db: Db) -> dict:
    expense_id = service.delete_line(db, principal.user_id, line_id)
    db.commit()
    return service.expense_with_lines_out(service.expense_with_lines(db, principal.user_id, expense_id))


# The calendar


def requested_month(text: str | None, today: date) -> tuple[str, date, date]:
    text = text or today.strftime("%Y-%m")
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}", text) or not 1 <= int(text[5:]) <= 12 \
            or not 2000 <= int(text[:4]) <= 2999:
        raise ApiError(400, "請選擇 2000 至 2999 年的有效月份（YYYY-MM）。")
    year, number = int(text[:4]), int(text[5:])
    return text, date(year, number, 1), date(year, number, monthrange(year, number)[1])


@router.get("/calendar")
def calendar_month(request: Request, principal: Signed, db: Db, month: str | None = Query(None)) -> dict:
    """Each day's total paid, count and merchants; the month's total."""
    today = clock.today(request.app.state.settings.timezone)
    text, first, last = requested_month(month, today)
    days = service.month(db, principal.user_id, first, last)
    return {"month": text, "today": today,
            "total": service.money(sum((total for _, total, _, _ in days), Decimal("0.00"))),
            "days": [{"date": day, "total": service.money(total), "count": count, "merchants": merchants}
                     for day, total, count, merchants in days]}


@router.get("/calendar/day")
def calendar_day(principal: Signed, db: Db, date_: str = Query(..., alias="date")) -> dict:
    """One day's expenses, each with its lines and summary."""
    try:
        day = date.fromisoformat(date_) if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", date_) else None
    except ValueError:
        day = None
    if day is None:
        raise ApiError(400, "請選擇有效的日期（YYYY-MM-DD）。")
    expenses = service.day_expenses(db, principal.user_id, day)
    return {"date": day, "total": service.money(sum((e.amount for e in expenses), Decimal("0.00"))),
            "expenses": [service.expense_with_lines_out(expense) for expense in expenses]}

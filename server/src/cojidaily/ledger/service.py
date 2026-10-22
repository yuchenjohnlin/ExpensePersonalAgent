"""The ledger's rules. Every function takes the owner and touches only that owner's rows; a row of
another owner is "not found". Writes lock the expense row they change, so two edits of one
expense (or of its lines) happen one after the other."""
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, selectinload

from ..platform import clock
from ..platform.errors import ApiError, invalid, not_found
from .adjustments import breakdown
from .lines import FIELDS, check_line, fill_derived, price_per_lb
from .models import Category, Expense, Line

DEFAULT_CATEGORIES = ("食材", "外食", "生活用品", "交通", "保險", "訂閱", "娛樂", "其他")
UNCATEGORIZED = ("未分類", "uncategorized")
HEADER = ("title", "amount", "date", "category_id", "merchant", "notes")
ADJUSTMENTS = ("tax", "tip", "receipt_discount")


# Categories


def ensure_categories(db: Session, owner: uuid.UUID) -> None:
    """A new account's categories: the old app's eight, then the system's 未分類."""
    if db.scalar(select(exists().where(Category.owner_id == owner))):
        return
    moment = clock.now()
    names = [(name, None) for name in DEFAULT_CATEGORIES] + [UNCATEGORIZED]
    db.add_all([Category(owner_id=owner, name=name, position=position, system_key=key, created_at=moment)
                for position, (name, key) in enumerate(names, 1)])
    db.flush()


def categories(db: Session, owner: uuid.UUID) -> list[Category]:
    return list(db.scalars(select(Category).where(Category.owner_id == owner).order_by(Category.position, Category.id)))


def uncategorized_id(db: Session, owner: uuid.UUID) -> int:
    ensure_categories(db, owner)
    return db.scalar(select(Category.id).where(Category.owner_id == owner, Category.system_key == UNCATEGORIZED[1]))


def owned_category(db: Session, owner: uuid.UUID, category_id: int) -> Category:
    category = db.scalar(select(Category).where(Category.id == category_id, Category.owner_id == owner))
    if category is None:
        raise invalid({"category_id": ["請選擇有效的分類。"]})
    return category


# Expenses


def check_paid_covers(amount: Decimal, tax: Decimal | None, tip: Decimal, field: str) -> None:
    """What the items cost before tax and tip (amount - tax - tip) must stay above zero."""
    if (tax or 0) + tip >= amount:
        raise invalid({field: ["稅加小費不能等於或超過實付金額。"]})


def create_expense(db: Session, owner: uuid.UUID, values: dict, *, reviewed: bool) -> Expense:
    """values: title, amount, date, category_id, merchant, notes, tax, tip, receipt_discount (clean).
    reviewed=False is an expense posted automatically, not looked at yet."""
    owned_category(db, owner, values["category_id"])
    check_paid_covers(values["amount"], values["tax"], values["tip"], "tax" if values["tax"] else "tip")
    moment = clock.now()
    expense = Expense(owner_id=owner, **{name: values[name] for name in HEADER + ADJUSTMENTS}, total_only=False,
                      reviewed_at=moment if reviewed else None, created_at=moment, updated_at=moment)
    db.add(expense)
    db.flush()
    return expense


def locked_expense(db: Session, owner: uuid.UUID, expense_id: int) -> Expense:
    """The expense, its row locked until the transaction ends.

    The lock is taken by a query on ledger_expense alone. Loading the expense joins its category,
    and a locking query with a join goes wrong under a concurrent edit: after waiting for the lock,
    PostgreSQL re-checks the newer row against the join's old category row, and if the other edit
    changed category_id the expense is not returned at all (it answered 404)."""
    locked = db.scalar(select(Expense.id).where(Expense.id == expense_id, Expense.owner_id == owner).with_for_update())
    if locked is None:
        raise not_found("支出")
    return db.get(Expense, locked, populate_existing=True)


def update_expense(db: Session, owner: uuid.UUID, expense_id: int, changes: dict) -> Expense:
    """changes: any of the header fields, tax / tip / receipt_discount, total_only, reviewed (clean)."""
    expense = locked_expense(db, owner, expense_id)
    if "category_id" in changes:
        owned_category(db, owner, changes["category_id"])
    for name in HEADER + ADJUSTMENTS:
        if name in changes:
            setattr(expense, name, changes[name])
    if "total_only" in changes:
        # Under the expense's row lock, so a line cannot be added in between.
        if changes["total_only"] and db.scalar(select(exists().where(Line.expense_id == expense.id))):
            raise ApiError(409, "這筆已有品項，不能標記為只有總額；請先刪除品項。")
        expense.total_only = changes["total_only"]
    field = "amount" if "amount" in changes else "tip" if "tip" in changes else "tax"
    check_paid_covers(expense.amount, expense.tax, expense.tip, field)
    if "reviewed" in changes:
        expense.reviewed_at = (expense.reviewed_at or clock.now()) if changes["reviewed"] else None
    expense.updated_at = clock.now()
    db.flush()
    return expense


def delete_expense(db: Session, owner: uuid.UUID, expense_id: int) -> None:
    """The expense and its lines. Other modules' links to them go with them (ON DELETE CASCADE)."""
    db.delete(locked_expense(db, owner, expense_id))
    db.flush()


# Lines


def line_text(value) -> str | None:
    if value is None:
        return None
    return format(value, "f") if isinstance(value, Decimal) else value


def add_line(db: Session, owner: uuid.UUID, expense_id: int, values: dict) -> Line:
    expense = locked_expense(db, owner, expense_id)
    if expense.total_only:
        raise ApiError(409, "這筆標記為只有總額，不能新增品項；請先取消標記。")
    clean, errors = check_line(values)
    if errors:
        raise invalid(errors)
    moment = clock.now()
    line = Line(expense_id=expense.id, **clean, derived_field="", created_at=moment, updated_at=moment)
    fill_derived(line)
    db.add(line)
    expense.updated_at = moment
    db.flush()
    return line


def locked_line(db: Session, owner: uuid.UUID, line_id: int) -> Line:
    expense_id = db.scalar(select(Line.expense_id).join(Expense).where(Line.id == line_id, Expense.owner_id == owner))
    if expense_id is None:
        raise not_found("品項")
    locked_expense(db, owner, expense_id)
    return db.get(Line, line_id)


def update_line(db: Session, owner: uuid.UUID, line_id: int, changes: dict) -> Line:
    """changes: any of the line's fields as text. The rest keep their values; a value the server
    had derived and the user left alone is worked out again from the new figures."""
    line = locked_line(db, owner, line_id)
    merged = {name: line_text(getattr(line, name)) for name in FIELDS} | changes
    clean, errors = check_line(merged)
    if errors:
        raise invalid({name: messages for name, messages in errors.items()})
    previous_field = line.derived_field
    previous_value = getattr(line, previous_field) if previous_field else None
    for name, value in clean.items():
        setattr(line, name, value)
    fill_derived(line, previous_field, previous_value)
    line.updated_at = line.expense.updated_at = clock.now()
    db.flush()
    return line


def delete_line(db: Session, owner: uuid.UUID, line_id: int) -> int:
    line = locked_line(db, owner, line_id)
    expense_id = line.expense_id
    db.delete(line)
    db.flush()
    return expense_id


# Reads


def expense_with_lines(db: Session, owner: uuid.UUID, expense_id: int) -> Expense:
    expense = db.scalar(select(Expense).where(Expense.id == expense_id, Expense.owner_id == owner)
                        .options(selectinload(Expense.lines)).execution_options(populate_existing=True))
    if expense is None:
        raise not_found("支出")
    return expense


def month(db: Session, owner: uuid.UUID, first: date, last: date) -> list[tuple[date, Decimal, int, list[str]]]:
    """Each day with expenses: (day, total paid, how many, distinct merchants as first written)."""
    where = (Expense.owner_id == owner, Expense.date.between(first, last))
    totals = db.execute(select(Expense.date, func.sum(Expense.amount), func.count(Expense.id))
                        .where(*where).group_by(Expense.date).order_by(Expense.date)).all()
    merchants: dict[date, dict[str, str]] = {}
    for day, merchant in db.execute(select(Expense.date, Expense.merchant).where(*where).order_by(Expense.id)):
        name = merchant.strip() or "未填店家"
        merchants.setdefault(day, {}).setdefault(name.casefold(), name)
    return [(day, total, count, list(merchants.get(day, {}).values())) for day, total, count in totals]


def day_expenses(db: Session, owner: uuid.UUID, day: date) -> list[Expense]:
    return list(db.scalars(select(Expense).where(Expense.owner_id == owner, Expense.date == day)
                           .options(selectinload(Expense.lines)).order_by(Expense.id)
                           .execution_options(populate_existing=True)))


def unreviewed(db: Session, owner: uuid.UUID) -> list[Expense]:
    return list(db.scalars(select(Expense).where(Expense.owner_id == owner, Expense.reviewed_at.is_(None))
                           .options(selectinload(Expense.lines)).order_by(Expense.id.desc()).limit(200)))


def similar(db: Session, owner: uuid.UUID, day: date, amount: Decimal, merchant: str) -> list[int]:
    """Expenses that look like the same purchase: same day, same amount, same merchant ignoring case."""
    return list(db.scalars(select(Expense.id).where(
        Expense.owner_id == owner, Expense.date == day, Expense.amount == amount,
        func.lower(func.btrim(Expense.merchant)) == merchant.strip().lower()).order_by(Expense.id)))


# What the API answers


def money(value: Decimal | None) -> str | None:
    return None if value is None else format(value, ".2f")


def measure(value: Decimal | None) -> str | None:
    return None if value is None else format(value, ".6f")


def from_cents(value: int | None) -> str | None:
    return None if value is None else format(Decimal(value) / 100, ".2f")


def expense_out(expense: Expense) -> dict:
    return {"id": expense.id, "title": expense.title, "amount": money(expense.amount), "date": expense.date,
            "category": {"id": expense.category.id, "name": expense.category.name}, "merchant": expense.merchant,
            "notes": expense.notes, "tax": money(expense.tax), "tip": money(expense.tip),
            "receipt_discount": money(expense.receipt_discount), "total_only": expense.total_only,
            "reviewed_at": expense.reviewed_at, "line_count": len(expense.lines),
            "created_at": expense.created_at, "updated_at": expense.updated_at}


def line_out(line: Line, share) -> dict:
    return {"id": line.id, "expense_id": line.expense_id, "description": line.description,
            "quantity": measure(line.quantity), "unit": line.unit, "amount": money(line.amount),
            "discount": money(line.discount), "quoted_unit_price": measure(line.quoted_unit_price),
            "price_unit": line.price_unit, "net_weight": measure(line.net_weight), "weight_unit": line.weight_unit,
            "notes": line.notes, "derived_field": line.derived_field, "price_per_lb": measure(price_per_lb(line)),
            "net_amount": None if share is None else from_cents(share.net),
            "tax_share": None if share is None else from_cents(share.tax),
            "discount_share": None if share is None else from_cents(share.receipt_discount),
            "tip_share": None if share is None else from_cents(share.tip),
            "final_amount": None if share is None else from_cents(share.final)}


def expense_with_lines_out(expense: Expense) -> dict:
    """The expense, its lines with each one's share of tax, tip and discount, and how the lines
    add up against what was paid. The paid amount stays the truth; unrecorded is what the lines
    entered so far leave unexplained (0 once the receipt is fully itemized)."""
    lines = list(expense.lines)
    result = breakdown(expense, lines)
    known = [line for line in lines if line.amount is not None]
    summary = {"paid_total": money(expense.amount),
               "line_total": money(sum((line.amount for line in known), Decimal("0"))),
               "line_discount_total": money(sum((line.discount for line in known), Decimal("0"))),
               "net_total": from_cents(result.net_total), "subtotal": from_cents(result.subtotal),
               "tax_rate": measure(result.rate(result.tax)), "tip_rate": measure(result.rate(result.tip)),
               "receipt_discount_rate": measure(result.rate(result.receipt_discount)),
               "unrecorded": from_cents(result.unrecorded),
               "unknown_amount_count": len(lines) - len(known)}
    return expense_out(expense) | {"lines": [line_out(line, result.shares.get(line.id)) for line in lines],
                                   "summary": summary}


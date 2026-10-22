"""A receipt as the page shows it: its photos, its current reading, and what it was posted as.
Reads from photos, reading and ledger through their api.py, a few queries for a whole page."""
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ledger import api as ledger
from ..photos import api as photos
from ..reading import api as reading
from .models import Posting, Receipt, ReceiptReading

EXPENSE_GONE = "入帳的支出已被刪除。"


def state(receipt: Receipt) -> str:
    if receipt.posting is not None:
        return "posted"
    return "reading" if receipt.pipeline == "reading" else "needs_review"


def cards(db: Session, owner: uuid.UUID, receipts: list[Receipt]) -> list[dict]:
    ids = [receipt.id for receipt in receipts]
    latest = dict(db.execute(select(ReceiptReading.receipt_id, func.max(ReceiptReading.reading_id))
                             .where(ReceiptReading.receipt_id.in_(ids)).group_by(ReceiptReading.receipt_id)).all()) \
        if ids else {}
    views = reading.get_many(db, latest.values())
    shown = photos.describe(db, owner, [photo.photo_id for receipt in receipts for photo in receipt.photos])
    expenses = ledger.summaries(db, owner, [r.posting.expense_id for r in receipts if r.posting is not None])
    return [card(receipt, views.get(latest.get(receipt.id)), shown, expenses) for receipt in receipts]


def card(receipt: Receipt, view, shown: dict, expenses: dict) -> dict:
    current = state(receipt)
    reasons = list(receipt.review_reasons) if current == "needs_review" else []
    if current == "needs_review" and not reasons:
        reasons = [EXPENSE_GONE]
    posting = receipt.posting
    return {
        "id": receipt.id,
        "created_at": receipt.created_at,
        "state": current,  # reading, posted, needs_review
        "reasons": reasons,
        "photos": [{"id": photo.photo_id, "position": photo.position,
                    "original_name": shown[photo.photo_id].original_name,
                    "preview_url": shown[photo.photo_id].preview_url,
                    "thumbnail_url": shown[photo.photo_id].thumbnail_url,
                    "original_url": shown[photo.photo_id].original_url} for photo in receipt.photos],
        "reading": None if view is None else reading_out(view),
        "posting": None if posting is None else {
            "mode": posting.mode, "reading_id": posting.reading_id, "skipped": posting.skipped,
            "expense": expense_out(expenses.get(posting.expense_id))},
    }


def reading_out(view) -> dict:
    result = view.result or {}
    return {"id": view.id, "status": view.status, "provider": view.provider, "model": view.model,
            "merchant": result.get("merchant"), "date": result.get("date"), "amount": result.get("amount"),
            "tax": result.get("tax"), "item_count": len(result.get("items") or []), "checks": view.checks,
            "warnings": result.get("warnings") or [], "error_code": view.error_code,
            "error_message": view.error_message, "elapsed_ms": view.elapsed_ms, "completed_at": view.completed_at}


def expense_out(summary) -> dict | None:
    if summary is None:
        return None
    return {"id": summary.id, "title": summary.title, "merchant": summary.merchant, "date": summary.date,
            "amount": summary.amount, "category": summary.category, "reviewed_at": summary.reviewed_at,
            "line_count": summary.line_count}


def for_expenses(db: Session, owner: uuid.UUID, expense_ids: list[int]) -> dict[str, dict]:
    """{expense id: the card of the receipt posted as it} for those that came from a receipt."""
    if not expense_ids:
        return {}
    receipts = list(db.scalars(select(Receipt).join(Posting, Posting.receipt_id == Receipt.id)
                               .where(Receipt.owner_id == owner, Posting.expense_id.in_(expense_ids))))
    return {str(receipt.posting.expense_id): shown for receipt, shown in zip(receipts, cards(db, owner, receipts))}


def page_of(db: Session, owner: uuid.UUID, state_filter: str | None, page: int, size: int = 20):
    """(receipts newest first on this page, total matching, counts of reading and needs_review)."""
    posted = select(Posting.receipt_id).where(Posting.receipt_id == Receipt.id).exists()
    where = [Receipt.owner_id == owner]
    conditions = {"posted": posted, "reading": ~posted & (Receipt.pipeline == "reading"),
                  "needs_review": ~posted & (Receipt.pipeline == "done")}
    if state_filter:
        where.append(conditions[state_filter])
    total = db.scalar(select(func.count()).select_from(Receipt).where(*where))
    receipts = list(db.scalars(select(Receipt).where(*where).order_by(Receipt.id.desc())
                               .offset((page - 1) * size).limit(size)))
    counts = {name: db.scalar(select(func.count()).select_from(Receipt).where(Receipt.owner_id == owner, condition))
              for name, condition in conditions.items() if name != "posted"}
    return receipts, total, counts

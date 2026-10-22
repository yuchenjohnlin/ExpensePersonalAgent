"""Receipts from upload to ledger: upload, read in the background, post or set aside, unpost, read again."""
import uuid

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, sessionmaker

from ..ledger import api as ledger
from ..photos import api as photos
from ..platform import clock
from ..platform.blobstore import BlobStore
from ..platform.errors import ApiError, not_found
from ..platform.settings import Settings
from ..reading import api as reading
from .models import Posting, PostedLine, Receipt, ReceiptPhoto, ReceiptReading
from .posting import header_from, lines_from

AFTER_READING = "receipts.after_reading"
MAX_PHOTOS_PER_RECEIPT = 10


def upload(db: Session, settings: Settings, blobs: BlobStore, owner: uuid.UUID, files: list[tuple[str, bytes]],
           groups: list[list[int]], *, allow_duplicates: bool) -> list[Receipt]:
    """Store the photos, make one receipt per group (photo indices, in order) and queue each one's
    reading: one transaction, so either every receipt of the upload exists or none does."""
    photo_ids = photos.store(db, blobs, owner, "receipt_page", files, allow_duplicates=allow_duplicates)
    made = []
    for group in groups:
        moment = clock.now()
        receipt = Receipt(owner_id=owner, pipeline="reading", review_reasons=[], created_at=moment, updated_at=moment)
        db.add(receipt)
        db.flush()
        db.add_all([ReceiptPhoto(receipt_id=receipt.id, position=position, photo_id=photo_ids[index])
                    for position, index in enumerate(group, 1)])
        db.flush()
        start_reading(db, settings, receipt, [photo_ids[index] for index in group])
        made.append(receipt)
    return made


def start_reading(db: Session, settings: Settings, receipt: Receipt, photo_ids: list[int]) -> int:
    reading_id = reading.request(db, settings, receipt.owner_id, photo_ids, then_kind=AFTER_READING,
                                 then_payload={"receipt_id": receipt.id})
    db.add(ReceiptReading(reading_id=reading_id, receipt_id=receipt.id, created_at=clock.now()))
    receipt.pipeline, receipt.review_reasons, receipt.updated_at = "reading", [], clock.now()
    db.flush()
    return reading_id


def latest_reading_id(db: Session, receipt_id: int) -> int | None:
    return db.scalar(select(func.max(ReceiptReading.reading_id)).where(ReceiptReading.receipt_id == receipt_id))


def has_posting(db: Session, receipt_id: int) -> bool:
    return bool(db.scalar(select(exists().where(Posting.receipt_id == receipt_id))))


def after_reading(sessions: sessionmaker[Session], payload: dict, *, settings: Settings) -> None:
    """The worker's job once a receipt's reading is done: post it automatically if the checks allow,
    otherwise set it aside with the reasons. Safe to run twice; a stale reading (one superseded by
    a newer request) is ignored."""
    with sessions() as db:
        receipt = db.scalar(select(Receipt).where(Receipt.id == payload["receipt_id"]).with_for_update())
        if receipt is None or receipt.pipeline == "done" or latest_reading_id(db, receipt.id) != payload["reading_id"]:
            return
        reasons = [] if has_posting(db, receipt.id) else post_automatically(db, settings, receipt, payload["reading_id"])
        receipt.pipeline, receipt.review_reasons, receipt.updated_at = "done", reasons, clock.now()
        db.commit()


def post_automatically(db: Session, settings: Settings, receipt: Receipt, reading_id: int) -> list[str]:
    """Post the reading as an unreviewed expense in 未分類, or return why not."""
    view = reading.get_many(db, [reading_id])[reading_id]
    if view.status != "succeeded":
        return [f"讀取失敗：{view.error_message}"]
    header, reasons = header_from(view.result, clock.today(settings.timezone))
    reasons += view.checks
    if reasons:
        return reasons
    owner = receipt.owner_id
    similar = ledger.similar_expense_ids(db, owner, header["date"], header["amount"], header["merchant"])
    if similar:
        return [f"可能重複：同一天已有同店家、同金額的支出（#{similar[0]}）。"]
    header["category_id"] = ledger.uncategorized_category_id(db, owner)
    try:
        with db.begin_nested():  # a refusal halfway leaves nothing of the expense behind
            post(db, receipt, view.id, header, view.result, mode="auto")
    except ApiError as error:
        return [message for messages in (error.fields or {}).values() for message in messages] or [error.error]
    return []


def post(db: Session, receipt: Receipt, reading_id: int | None, header: dict, result: dict | None, *, mode: str) -> int:
    """Create the expense (with the read items as lines when a result is given) and the links."""
    lines, skipped = lines_from(result, ledger.check_line) if result is not None else ([], [])
    expense_id, line_ids = ledger.create_expense(db, receipt.owner_id, header, [values for _, values in lines],
                                                 reviewed=mode == "manual")
    db.add(Posting(receipt_id=receipt.id, expense_id=expense_id, reading_id=reading_id, mode=mode, skipped=skipped,
                   created_at=clock.now()))
    db.add_all([PostedLine(line_id=line_id, receipt_id=receipt.id, reading_id=reading_id, item_index=index)
                for line_id, (index, _) in zip(line_ids, lines)])
    db.flush()
    return expense_id


def locked_receipt(db: Session, owner: uuid.UUID, receipt_id: int) -> Receipt:
    receipt = db.scalar(select(Receipt).where(Receipt.id == receipt_id, Receipt.owner_id == owner).with_for_update())
    if receipt is None:
        raise not_found("收據")
    return receipt


def post_by_hand(db: Session, owner: uuid.UUID, receipt_id: int, header: dict, with_lines: bool) -> int:
    """Post a receipt set aside: the header as the user checked it, the current reading's items as
    lines if asked. Looked at by definition (reviewed)."""
    receipt = locked_receipt(db, owner, receipt_id)
    if has_posting(db, receipt.id):
        raise ApiError(409, "這張收據已經入帳。")
    if receipt.pipeline == "reading":
        raise ApiError(409, "這張收據還在讀取中。")
    reading_id = latest_reading_id(db, receipt.id)
    view = reading.get_many(db, [reading_id])[reading_id] if reading_id else None
    if with_lines and (view is None or view.status != "succeeded"):
        raise ApiError(400, "這張收據沒有讀取結果可以建立品項。")
    expense_id = post(db, receipt, view.id if view and with_lines else None, header,
                      view.result if with_lines else None, mode="manual")
    receipt.review_reasons, receipt.updated_at = [], clock.now()
    return expense_id


def unpost(db: Session, owner: uuid.UUID, receipt_id: int) -> int:
    """Delete the expense this receipt was posted as (its lines and the links go with it)."""
    receipt = locked_receipt(db, owner, receipt_id)
    posting = db.get(Posting, receipt.id)
    if posting is None:
        raise ApiError(409, "這張收據沒有入帳。")
    expense_id = posting.expense_id
    ledger.delete_expense(db, owner, expense_id)
    receipt.review_reasons, receipt.updated_at = ["已取消入帳。"], clock.now()
    db.flush()
    return expense_id


def read_again(db: Session, settings: Settings, owner: uuid.UUID, receipt_id: int) -> int:
    receipt = locked_receipt(db, owner, receipt_id)
    if has_posting(db, receipt.id):
        raise ApiError(409, "已入帳的收據要先取消入帳，才能重新讀取。")
    if receipt.pipeline == "reading":
        raise ApiError(409, "這張收據還在讀取中。")
    return start_reading(db, settings, receipt, [photo.photo_id for photo in receipt.photos])

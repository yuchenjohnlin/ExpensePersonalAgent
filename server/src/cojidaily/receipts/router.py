"""The receipt page's endpoints."""
import json
from math import ceil
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import StrictBool
from sqlalchemy import select

from ..auth.api import Signed
from ..ledger import api as ledger
from ..photos import api as photos
from ..platform.db import Db
from ..platform.errors import ApiError
from . import service, views
from .models import Receipt

router = APIRouter(prefix="/api")


async def received(request: Request) -> photos.Upload:
    return await photos.receive(request, photos.MAX_PHOTOS_PER_UPLOAD)


def refused(message: str) -> ApiError:
    return ApiError(400, message, {"photos": [message]})


def upload_options(upload: photos.Upload) -> tuple[list[list[int]], bool]:
    """groups: JSON lists of photo indices, each a receipt, covering every photo once (default: all
    photos are one receipt); allow_duplicates: "true" to save photos already stored."""
    count = len(upload.files)
    if not count:
        raise refused("請選擇至少一張收據照片。")
    if set(upload.fields) - {"groups", "allow_duplicates"} or any(len(v) != 1 for v in upload.fields.values()):
        raise refused("只接受 photos、groups 與 allow_duplicates 欄位，各一次。")
    flag = upload.fields.get("allow_duplicates", ["false"])[0]
    if flag not in ("true", "false"):
        raise refused("allow_duplicates 必須是 true 或 false。")
    if "groups" not in upload.fields:
        groups = [list(range(count))]
    else:
        try:
            groups = json.loads(upload.fields["groups"][0])
        except ValueError:
            raise refused("groups 必須是照片索引組成的 JSON 陣列。") from None
    if not isinstance(groups, list) or not groups or any(not isinstance(g, list) or not g for g in groups):
        raise refused("每組收據至少要有一張照片。")
    if any(len(group) > service.MAX_PHOTOS_PER_RECEIPT for group in groups):
        raise refused(f"每張收據最多 {service.MAX_PHOTOS_PER_RECEIPT} 張照片。")
    flat = [index for group in groups for index in group]
    if any(type(index) is not int for index in flat) or sorted(flat) != list(range(count)):
        raise refused("每張照片都要剛好屬於一組，索引從 0 開始。")
    return groups, flag == "true"


@router.post("/receipts", status_code=201)
def upload(principal: Signed, upload: Annotated[photos.Upload, Depends(received)], request: Request, db: Db) -> dict:
    """Photos from the receipt page as one or more receipts; each is read in the background."""
    groups, allow_duplicates = upload_options(upload)
    try:
        made = service.upload(db, request.app.state.settings, request.app.state.blobs, principal.user_id,
                              upload.files, groups, allow_duplicates=allow_duplicates)
    except photos.PhotoRejected as error:
        raise refused(error.message) from None
    except photos.DuplicatePhotos as error:
        raise ApiError(409, "照片已經上傳過；確認後可以選擇仍要保存。", duplicates=error.duplicates) from None
    db.commit()
    return {"receipts": views.cards(db, principal.user_id, made)}


@router.get("/receipts")
def receipts(principal: Signed, db: Db, state: Literal["reading", "needs_review", "posted"] | None = None,
             page: int = Query(1, ge=1)) -> dict:
    """Newest first, 20 a page; counts say how many are being read and how many need a look."""
    found, total, counts = views.page_of(db, principal.user_id, state, page)
    return {"receipts": views.cards(db, principal.user_id, found), "page": page,
            "pages": max(1, ceil(total / 20)), "total": total, "counts": counts}


@router.get("/receipts/for-expenses")
def for_expenses(principal: Signed, db: Db, expense_id: list[int] = Query(default=[], max_length=200)) -> dict:
    """The receipt each of these expenses was posted from, by expense id (expenses entered by hand
    have none). The ledger does not know receipts, so a page showing expenses asks here."""
    return {"receipts": views.for_expenses(db, principal.user_id, expense_id)}


def one(db, principal, receipt_id: int) -> dict:
    receipt = db.scalar(select(Receipt).where(Receipt.id == receipt_id, Receipt.owner_id == principal.user_id)
                        .execution_options(populate_existing=True))
    if receipt is None:
        raise ApiError(404, "找不到這張收據。")
    return views.cards(db, principal.user_id, [receipt])[0]


@router.get("/receipts/{receipt_id}")
def receipt(receipt_id: int, principal: Signed, db: Db) -> dict:
    return one(db, principal, receipt_id)


@router.post("/receipts/{receipt_id}/readings", status_code=202)
def read_again(receipt_id: int, request: Request, principal: Signed, db: Db) -> dict:
    service.read_again(db, request.app.state.settings, principal.user_id, receipt_id)
    db.commit()
    return one(db, principal, receipt_id)


class PostingIn(ledger.ExpenseHeader):
    lines: StrictBool = False  # also make the current reading's items into lines


@router.post("/receipts/{receipt_id}/posting", status_code=201)
def post_by_hand(receipt_id: int, body: PostingIn, principal: Signed, db: Db) -> dict:
    header = body.model_dump(exclude={"lines"})
    service.post_by_hand(db, principal.user_id, receipt_id, header, body.lines)
    db.commit()
    return one(db, principal, receipt_id)


@router.delete("/receipts/{receipt_id}/posting")
def unpost(receipt_id: int, principal: Signed, db: Db) -> dict:
    service.unpost(db, principal.user_id, receipt_id)
    db.commit()
    return one(db, principal, receipt_id)

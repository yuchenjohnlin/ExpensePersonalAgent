"""The MVP's path end to end (pm/decisions/mvp-receipt-page-slice.md): upload on the receipt page,
read in the background, post automatically or set aside, then fix by hand."""
import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from cojidaily.platform import clock
from cojidaily.receipts import service
from cojidaily.receipts.models import PostedLine

from .conftest import make_user, sign_in
from .fake_vllm import completion, receipt
from .photo_samples import drawing


def upload(client, count=1, groups=None, first_shade=0, **fields):
    files = [("photos", (f"{n}.png", drawing(shade=n), "image/png")) for n in range(first_shade, first_shade + count)]
    data = dict(fields)
    if groups is not None:
        data["groups"] = json.dumps(groups)
    return client.post("/api/receipts", files=files, data=data)


def uploaded(client, *args, **kwargs) -> list[dict]:
    response = upload(client, *args, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()["receipts"]


def card(client, receipt_id):
    return client.get(f"/api/receipts/{receipt_id}").json()


def test_an_upload_becomes_receipts_that_wait_for_their_reading(signed):
    receipts = uploaded(signed, 3, groups=[[0, 1], [2]])
    assert [r["state"] for r in receipts] == ["reading", "reading"]
    assert [len(r["photos"]) for r in receipts] == [2, 1]
    first = receipts[0]
    assert first["reading"]["status"] == "queued" and first["posting"] is None
    assert first["photos"][0]["preview_url"] == f"/api/photos/{first['photos'][0]['id']}/preview"
    assert signed.get(first["photos"][0]["thumbnail_url"]).headers["content-type"] == "image/jpeg"
    listing = signed.get("/api/receipts").json()
    assert listing["counts"] == {"reading": 2, "needs_review": 0} and listing["total"] == 2


def test_a_clean_reading_is_posted_as_an_unreviewed_uncategorized_expense(signed, worker, sessions):
    [made] = uploaded(signed)
    assert worker.run_until_idle() == 2  # reading.run, then receipts.after_reading
    posted = card(signed, made["id"])
    assert posted["state"] == "posted" and posted["reasons"] == []
    assert posted["reading"]["status"] == "succeeded" and posted["reading"]["merchant"] == "Kroger"
    expense = posted["posting"]["expense"]
    assert posted["posting"]["mode"] == "auto" and posted["posting"]["skipped"] == []
    assert (expense["title"], expense["amount"], expense["date"], expense["category"], expense["reviewed_at"],
            expense["line_count"]) == ("Kroger", "4.68", "2026-10-09", "未分類", None, 2)
    # The ledger has it, unreviewed, with lines that remember which read item they were.
    [waiting] = signed.get("/api/expenses/unreviewed").json()
    assert waiting["id"] == expense["id"] and waiting["tax"] == "0.14"
    bananas = waiting["lines"][0]
    assert (bananas["description"], bananas["net_weight"], bananas["weight_unit"], bananas["amount"]) == (
        "BANANAS", "2.850000", "lb", "1.57")
    assert signed.get("/api/calendar/day?date=2026-10-09").json()["total"] == "4.68"
    with sessions() as db:
        assert [(p.line_id, p.item_index) for p in db.scalars(select(PostedLine).order_by(PostedLine.item_index))] == [
            (line["id"], index) for index, line in enumerate(waiting["lines"], 1)]


def test_the_same_purchase_twice_is_set_aside_as_a_likely_duplicate(signed, worker):
    first, second = uploaded(signed, 2, groups=[[0], [1]])
    worker.run_until_idle()
    assert card(signed, first["id"])["state"] == "posted"
    again = card(signed, second["id"])
    expense_id = card(signed, first["id"])["posting"]["expense"]["id"]
    assert again["state"] == "needs_review"
    assert again["reasons"] == [f"可能重複：同一天已有同店家、同金額的支出（#{expense_id}）。"]


@pytest.mark.parametrize("draft, reasons", [
    (receipt(amount="5.00"), ["小計加稅與小費、減整張折扣，與總額不一致；未自動修改任何讀取值。"]),
    (receipt(merchant=None, date=None), ["讀不到店家、日期。"]),
    (receipt(date=(clock.today("America/New_York") + timedelta(days=2)).isoformat()), ["讀到的日期在未來。"]),
    (receipt(tax="0.145"), ["讀到的金額不是兩位小數的金額。"]),
    (receipt(tax="4.00", subtotal="0.68"), ["品項金額加總與小計不一致；可能有漏讀、重複或折扣，請核對原照。"]),
])
def test_readings_that_fail_a_check_wait_for_a_look(signed, worker, vllm, draft, reasons):
    vllm.reset((200, completion(draft)))
    [made] = uploaded(signed)
    worker.run_until_idle()
    waiting = card(signed, made["id"])
    assert waiting["state"] == "needs_review" and waiting["reasons"] == reasons
    assert signed.get("/api/receipts?state=needs_review").json()["counts"]["needs_review"] == 1
    assert signed.get("/api/expenses/unreviewed").json() == []


def test_a_receipt_set_aside_is_posted_by_hand_with_its_read_items(signed, worker, vllm):
    vllm.reset((200, completion(receipt(amount="5.00"))))
    [made] = uploaded(signed)
    worker.run_until_idle()
    categories = {c["name"]: c["id"] for c in signed.get("/api/categories").json()}
    body = {"title": "Kroger", "amount": "4.68", "date": "2026-10-09", "category_id": categories["食材"],
            "merchant": "Kroger", "tax": "0.14", "lines": True}
    posted = signed.post(f"/api/receipts/{made['id']}/posting", json=body)
    assert posted.status_code == 201, posted.text
    result = posted.json()
    assert result["state"] == "posted" and result["posting"]["mode"] == "manual"
    assert result["posting"]["expense"]["category"] == "食材"
    assert result["posting"]["expense"]["reviewed_at"] is not None  # posted by hand = looked at
    assert result["posting"]["expense"]["line_count"] == 2
    assert signed.post(f"/api/receipts/{made['id']}/posting", json=body).status_code == 409


def test_a_failed_reading_can_be_read_again(signed, worker, vllm):
    vllm.reset((500, {"error": "down"}))
    [made] = uploaded(signed)
    worker.run_until_idle()
    failed = card(signed, made["id"])
    assert failed["state"] == "needs_review"
    assert failed["reasons"] == ["讀取失敗：讀取服務拒絕請求或暫時失敗。"]
    vllm.reset()
    again = signed.post(f"/api/receipts/{made['id']}/readings")
    assert again.status_code == 202 and again.json()["state"] == "reading"
    assert signed.post(f"/api/receipts/{made['id']}/readings").status_code == 409  # already reading
    worker.run_until_idle()
    assert card(signed, made["id"])["state"] == "posted"
    assert signed.post(f"/api/receipts/{made['id']}/readings").status_code == 409  # posted


def test_unposting_deletes_the_expense_and_sets_the_receipt_aside(signed, worker):
    [made] = uploaded(signed)
    worker.run_until_idle()
    expense_id = card(signed, made["id"])["posting"]["expense"]["id"]
    after = signed.delete(f"/api/receipts/{made['id']}/posting").json()
    assert after["state"] == "needs_review" and after["reasons"] == ["已取消入帳。"]
    assert signed.get(f"/api/expenses/{expense_id}").status_code == 404
    assert signed.delete(f"/api/receipts/{made['id']}/posting").status_code == 409


def test_deleting_the_expense_in_the_ledger_sets_the_receipt_aside(signed, worker):
    [made] = uploaded(signed)
    worker.run_until_idle()
    expense_id = card(signed, made["id"])["posting"]["expense"]["id"]
    signed.delete(f"/api/expenses/{expense_id}")
    gone = card(signed, made["id"])
    assert gone["state"] == "needs_review" and gone["reasons"] == ["入帳的支出已被刪除。"]


def test_a_deduction_that_belongs_to_no_item_is_skipped_but_the_receipt_still_posts(signed, worker, vllm):
    draft = receipt(subtotal="3.54", amount="3.68")
    draft["items"].append(draft["items"][1] | {"description": "COUPON", "amount": "-1.00"})
    vllm.reset((200, completion(draft)))
    [made] = uploaded(signed)
    worker.run_until_idle()
    posted = card(signed, made["id"])
    assert posted["state"] == "posted" and posted["posting"]["expense"]["line_count"] == 2
    assert posted["posting"]["skipped"] == [{"index": 3, "description": "COUPON", "amount": "-1.00",
                                             "reason": "負數（折價），請在折扣欄補上"}]


def test_a_superseded_reading_is_ignored(signed, worker, vllm, app, settings):
    vllm.reset((500, {"error": "down"}))
    [made] = uploaded(signed)
    worker.run_until_idle()
    old_reading = card(signed, made["id"])["reading"]["id"]
    signed.post(f"/api/receipts/{made['id']}/readings")
    # The old reading's job running again (at-least-once) must not decide anything now.
    service.after_reading(app.state.sessions, {"receipt_id": made["id"], "reading_id": old_reading}, settings=settings)
    assert card(signed, made["id"])["state"] == "reading"


@pytest.mark.parametrize("count, groups, message", [
    (2, [[0]], "每張照片都要剛好屬於一組，索引從 0 開始。"),
    (2, [[0, 1], [1]], "每張照片都要剛好屬於一組，索引從 0 開始。"),
    (2, [[0], []], "每組收據至少要有一張照片。"),
    (11, [list(range(11))], "每張收據最多 10 張照片。"),
    (1, "not json", "groups 必須是照片索引組成的 JSON 陣列。"),
])
def test_bad_groups_are_refused_and_nothing_is_saved(signed, count, groups, message):
    files = [("photos", (f"{n}.png", drawing(size=(60, 40), shade=n), "image/png")) for n in range(count)]
    data = {"groups": groups if isinstance(groups, str) else json.dumps(groups)}
    response = signed.post("/api/receipts", files=files, data=data)
    assert (response.status_code, response.json()["fields"]["photos"]) == (400, [message])
    assert signed.get("/api/receipts").json()["total"] == 0


def test_uploads_need_photos_that_are_photos(signed):
    response = signed.post("/api/receipts", files=[("photos", ("a.txt", b"hello", "text/plain"))])
    assert response.json()["fields"]["photos"] == ["照片無法讀取，請重新拍照或選擇其他圖片。"]
    assert signed.post("/api/receipts", files=[("other", ("a.png", drawing(), "image/png"))]).status_code == 400
    assert signed.post("/api/receipts", json={}).json()["error"] == "請使用 multipart/form-data 上傳照片。"


def test_a_photo_uploaded_again_is_refused_until_confirmed(signed):
    uploaded(signed)
    again = upload(signed)
    assert again.status_code == 409
    assert again.json()["duplicates"] == [{"index": 0, "existing_photo_ids": [1], "same_as_indices": []}]
    assert signed.get("/api/receipts").json()["total"] == 1
    assert len(uploaded(signed, allow_duplicates="true")) == 1


def test_receipts_belong_to_their_owner(client, sessions, owner, worker):
    sign_in(client)
    [made] = uploaded(client)
    client.post("/api/auth/logout")
    assert upload(client).status_code == 401  # refused before the photos are stored
    make_user(sessions, "someone")
    sign_in(client, "someone")
    assert client.get(f"/api/receipts/{made['id']}").status_code == 404
    assert client.get("/api/receipts").json()["total"] == 0
    assert client.post(f"/api/receipts/{made['id']}/readings").status_code == 404


def test_expenses_find_the_receipt_they_came_from(signed, worker):
    [made] = uploaded(signed)
    worker.run_until_idle()
    expense_id = card(signed, made["id"])["posting"]["expense"]["id"]
    categories = {c["name"]: c["id"] for c in signed.get("/api/categories").json()}
    by_hand = signed.post("/api/expenses", json={"title": "Lunch", "amount": "9.00", "date": "2026-10-09",
                                                 "category_id": categories["外食"]}).json()["id"]
    found = signed.get(f"/api/receipts/for-expenses?expense_id={expense_id}&expense_id={by_hand}").json()["receipts"]
    assert list(found) == [str(expense_id)] and found[str(expense_id)]["id"] == made["id"]
    assert signed.get("/api/receipts/for-expenses").json() == {"receipts": {}}

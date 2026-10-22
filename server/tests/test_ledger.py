"""The ledger's HTTP API: categories, expenses, lines, review status and the calendar."""
from datetime import date

import pytest

from cojidaily.ledger import api as ledger
from cojidaily.platform.errors import ApiError

from .conftest import make_user, sign_in


def category_id(client, name="食材"):
    return next(c["id"] for c in client.get("/api/categories").json() if c["name"] == name)


def expense(client, **values):
    body = {"title": "Kroger", "amount": "10.70", "date": "2026-10-09", "category_id": category_id(client)} | values
    response = client.post("/api/expenses", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_a_new_account_has_the_eight_categories_and_uncategorized(signed):
    names = [(c["name"], c["system"]) for c in signed.get("/api/categories").json()]
    assert names == [("食材", False), ("外食", False), ("生活用品", False), ("交通", False), ("保險", False),
                     ("訂閱", False), ("娛樂", False), ("其他", False), ("未分類", True)]


def test_a_hand_entered_expense_is_reviewed_and_answered_whole(signed):
    body = expense(signed, merchant="Kroger", tax="0.70")
    assert body["amount"] == "10.70" and body["tax"] == "0.70" and body["tip"] == "0.00"
    assert body["category"]["name"] == "食材"
    assert body["reviewed_at"] is not None
    assert body["lines"] == [] and body["summary"]["unrecorded"] == "10.00"


@pytest.mark.parametrize("values, field, message", [
    ({"amount": "0"}, "amount", "金額必須大於 0。"),
    ({"amount": 12.5}, "amount", "請以文字填寫數字。"),
    ({"amount": "1.005"}, "amount", "小數最多 2 位。"),
    ({"date": "10/09/2026"}, "date", "請使用 YYYY-MM-DD 的日期。"),
    ({"title": "  "}, "title", "此為必需欄位。"),
    ({"tax": "6", "tip": "5"}, "tax", "稅加小費不能等於或超過實付金額。"),
    ({"category_id": 999999}, "category_id", "請選擇有效的分類。"),
    ({"surprise": 1}, "surprise", "不支援的欄位。"),
])
def test_bad_expenses_are_refused_by_field(signed, values, field, message):
    body = {"title": "Kroger", "amount": "10.70", "date": "2026-10-09", "category_id": category_id(signed)} | values
    response = signed.post("/api/expenses", json=body)
    assert response.status_code == 400
    assert response.json()["fields"][field] == [message]


def test_another_owner_s_rows_do_not_exist(client, sessions, signed):
    mine = expense(signed)
    make_user(sessions, "someone")
    sign_in(client, "someone")
    assert client.get(f"/api/expenses/{mine['id']}").status_code == 404
    assert client.patch(f"/api/expenses/{mine['id']}", json={"title": "x"}).status_code == 404
    assert client.delete(f"/api/expenses/{mine['id']}").status_code == 404
    # Nor can one use another owner's category.
    response = client.post("/api/expenses", json={"title": "x", "amount": "1.00", "date": "2026-10-09",
                                                  "category_id": mine["category"]["id"]})
    assert response.json()["fields"] == {"category_id": ["請選擇有效的分類。"]}


def test_patch_changes_only_what_is_sent(signed):
    made = expense(signed, merchant="Kroger", notes="weekly", tax="0.70")
    body = signed.patch(f"/api/expenses/{made['id']}", json={"title": "Kroger groceries", "tax": None}).json()
    assert (body["title"], body["merchant"], body["notes"], body["tax"]) == ("Kroger groceries", "Kroger", "weekly", None)
    assert signed.patch(f"/api/expenses/{made['id']}", json={"title": None}).json()["fields"] == {
        "title": ["此為必需欄位。"]}
    assert signed.patch(f"/api/expenses/{made['id']}", json={"amount": "0.50", "tip": "0.60"}).json()["fields"] == {
        "amount": ["稅加小費不能等於或超過實付金額。"]}
    assert signed.patch(f"/api/expenses/{made['id']}", json={}).status_code == 400


def test_lines_derive_what_they_can_and_keep_what_was_typed(signed):
    made = expense(signed, amount="5.70")
    body = signed.post(f"/api/expenses/{made['id']}/lines",
                       json={"description": "BANANAS", "amount": "5.70", "quantity": "2", "unit": "each"}).json()
    line = body["lines"][0]
    assert body["line_id"] == line["id"]
    assert (line["quoted_unit_price"], line["price_unit"], line["derived_field"]) == ("2.850000", "each", "quoted_unit_price")
    changed = signed.patch(f"/api/lines/{line['id']}", json={"amount": "6.00"}).json()["lines"][0]
    assert (changed["id"], changed["quoted_unit_price"], changed["derived_field"]) == (line["id"], "3.000000", "quoted_unit_price")
    typed = signed.patch(f"/api/lines/{line['id']}", json={"quoted_unit_price": "2.99"}).json()["lines"][0]
    assert (typed["quoted_unit_price"], typed["derived_field"]) == ("2.990000", "")
    refused = signed.patch(f"/api/lines/{line['id']}", json={"discount": "9"})
    assert refused.json()["fields"] == {"discount": ["折扣不能超過原價。"]}
    after = signed.delete(f"/api/lines/{line['id']}").json()
    assert after["lines"] == []


def test_lines_get_their_share_of_tax_and_the_summary_checks_them_against_the_total(signed):
    made = expense(signed, amount="10.70", tax="0.70")
    signed.post(f"/api/expenses/{made['id']}/lines", json={"description": "MILK", "amount": "6.00"})
    body = signed.post(f"/api/expenses/{made['id']}/lines", json={"description": "EGGS", "amount": "4.00"}).json()
    assert [(line["tax_share"], line["final_amount"]) for line in body["lines"]] == [("0.42", "6.42"), ("0.28", "4.28")]
    assert (body["summary"]["subtotal"], body["summary"]["unrecorded"], body["summary"]["tax_rate"]) == (
        "10.00", "0.00", "0.070000")


def test_total_only_and_lines_exclude_each_other(signed):
    made = expense(signed)
    signed.post(f"/api/expenses/{made['id']}/lines", json={"description": "MILK", "amount": "1.00"})
    refused = signed.patch(f"/api/expenses/{made['id']}", json={"total_only": True})
    assert (refused.status_code, refused.json()["error"]) == (409, "這筆已有品項，不能標記為只有總額；請先刪除品項。")
    other = expense(signed)
    assert signed.patch(f"/api/expenses/{other['id']}", json={"total_only": True}).json()["total_only"] is True
    assert signed.post(f"/api/expenses/{other['id']}/lines", json={"description": "X"}).status_code == 409


def test_auto_posted_expenses_wait_in_unreviewed_until_looked_at(signed, sessions, owner):
    with sessions() as db:
        header = {"title": "Kroger", "amount": ledger.Decimal("4.68"), "date": date(2026, 10, 9),
                  "category_id": ledger.uncategorized_category_id(db, owner), "merchant": "Kroger", "notes": "",
                  "tax": ledger.Decimal("0.14"), "tip": ledger.Decimal("0"), "receipt_discount": ledger.Decimal("0")}
        clean, reason = ledger.check_line({"description": "BANANAS", "amount": "1.57", "net_weight": "2.85",
                                           "weight_unit": "lb"})
        assert reason == ""
        expense_id, line_ids = ledger.create_expense(db, owner, header, [clean], reviewed=False)
        db.commit()
    waiting = signed.get("/api/expenses/unreviewed").json()
    assert [(e["id"], e["category"]["name"], e["reviewed_at"]) for e in waiting] == [(expense_id, "未分類", None)]
    assert waiting[0]["lines"][0]["id"] == line_ids[0]
    seen = signed.patch(f"/api/expenses/{expense_id}", json={"reviewed": True}).json()
    assert seen["reviewed_at"] is not None
    assert signed.get("/api/expenses/unreviewed").json() == []
    with sessions() as db:
        summary = ledger.summaries(db, owner, [expense_id])[expense_id]
    assert (summary.amount, summary.category, summary.line_count) == ("4.68", "未分類", 1)


def test_the_ledger_api_refuses_a_bad_header_before_writing(sessions, owner):
    with sessions() as db:
        header = {"title": "X", "amount": ledger.Decimal("1.00"), "date": date(2026, 10, 9),
                  "category_id": ledger.uncategorized_category_id(db, owner), "merchant": "", "notes": "",
                  "tax": ledger.Decimal("1.00"), "tip": ledger.Decimal("0"), "receipt_discount": ledger.Decimal("0")}
        with pytest.raises(ApiError):
            ledger.create_expense(db, owner, header, [], reviewed=False)
        assert ledger.similar_expense_ids(db, owner, date(2026, 10, 9), ledger.Decimal("1.00"), "") == []


def test_the_calendar_totals_each_day_and_lists_its_merchants(signed):
    expense(signed, amount="10.00", merchant="Kroger", date="2026-10-09")
    expense(signed, amount="2.50", merchant=" kroger ", date="2026-10-09")
    expense(signed, amount="7.25", merchant="", date="2026-10-11")
    expense(signed, amount="99.00", merchant="Elsewhere", date="2026-11-01")
    month = signed.get("/api/calendar?month=2026-10").json()
    assert month["total"] == "19.75"
    assert month["days"] == [{"date": "2026-10-09", "total": "12.50", "count": 2, "merchants": ["Kroger"]},
                             {"date": "2026-10-11", "total": "7.25", "count": 1, "merchants": ["未填店家"]}]
    day = signed.get("/api/calendar/day?date=2026-10-09").json()
    assert day["total"] == "12.50" and [e["amount"] for e in day["expenses"]] == ["10.00", "2.50"]
    assert signed.get("/api/calendar?month=2026-13").status_code == 400
    assert signed.get("/api/calendar/day?date=2026-02-30").status_code == 400


def test_two_edits_of_one_expense_at_once_both_land(signed, sessions, owner):
    """One edit changes the category while the other waits for the row lock to change the date;
    the waiting one must still find the expense (it used to get 404, see locked_expense)."""
    import threading

    from cojidaily.ledger import service

    made = expense(signed)
    other = category_id(signed, "外食")
    result = {}
    with sessions() as first:
        service.update_expense(first, owner, made["id"], {"category_id": other})  # holds the lock

        def second_edit():
            with sessions() as db:
                try:
                    service.update_expense(db, owner, made["id"], {"date": date(2026, 9, 27)})
                    db.commit()
                    result["ok"] = True
                except ApiError as error:
                    result["error"] = error.status

        waiting = threading.Thread(target=second_edit)
        waiting.start()
        waiting.join(0.5)  # it is blocked on the lock now
        first.commit()
        waiting.join(5)
    assert result == {"ok": True}
    body = signed.get(f"/api/expenses/{made['id']}").json()
    assert (body["date"], body["category"]["name"]) == ("2026-09-27", "外食")


def test_deleting_an_expense_takes_its_lines(signed):
    made = expense(signed)
    signed.post(f"/api/expenses/{made['id']}/lines", json={"description": "MILK", "amount": "1.00"})
    assert signed.delete(f"/api/expenses/{made['id']}").json() == {"deleted": made["id"]}
    assert signed.get(f"/api/expenses/{made['id']}").status_code == 404

"""A line's checks, its derived measure and the tax / tip / discount split (ledger/lines.py, adjustments.py)."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from cojidaily.ledger.adjustments import allocate, breakdown
from cojidaily.ledger.lines import check_line, fill_derived, price_per_lb

D = Decimal


def line(**values):
    fields = dict(amount=None, quantity=None, unit="", quoted_unit_price=None, price_unit="", net_weight=None,
                  weight_unit="", discount=D("0"), derived_field="")
    return SimpleNamespace(**(fields | values))


def test_a_count_and_an_amount_give_the_unit_price():
    item = line(amount=D("5.70"), quantity=D("2"), unit="each")
    fill_derived(item)
    assert (item.quoted_unit_price, item.price_unit, item.derived_field) == (D("2.850000"), "each", "quoted_unit_price")


def test_a_per_pound_price_gives_the_weight_in_the_line_s_weight_unit():
    item = line(amount=D("1.57"), quoted_unit_price=D("0.55"), price_unit="lb", weight_unit="kg")
    fill_derived(item)
    assert item.derived_field == "net_weight" and item.weight_unit == "kg"
    assert item.net_weight == D("1.294800")  # 1.57 / 0.55 = 2.854545 lb


def test_weight_wins_over_a_count_without_a_price_unit():
    item = line(amount=D("4.00"), quantity=D("2"), unit="each", net_weight=D("2"), weight_unit="lb")
    fill_derived(item)
    assert (item.quoted_unit_price, item.price_unit) == (D("2.000000"), "lb")


def test_nothing_is_derived_from_a_zero_or_unknown_amount_or_when_both_sides_are_known():
    for item in (line(amount=None, quantity=D("2"), unit="each"), line(amount=D("0"), quantity=D("2"), unit="each"),
                 line(amount=D("3"), quantity=D("2"), unit="each", quoted_unit_price=D("1.4"), price_unit="each")):
        fill_derived(item)
        assert item.derived_field == ""
    assert line(amount=D("3"), quantity=D("2"), unit="each", quoted_unit_price=D("1.4"), price_unit="each") \
        .quoted_unit_price == D("1.4")  # a typed value is never changed


def test_an_untouched_derived_value_is_worked_out_again_but_a_typed_one_stays():
    item = line(amount=D("6.00"), quantity=D("2"), unit="each")
    fill_derived(item)
    assert item.quoted_unit_price == D("3.000000")
    item.amount = D("8.00")  # the user changed the amount, left the derived price alone
    fill_derived(item, "quoted_unit_price", D("3.000000"))
    assert (item.quoted_unit_price, item.derived_field) == (D("4.000000"), "quoted_unit_price")
    item.quoted_unit_price = D("3.50")  # now the user typed a price
    fill_derived(item, "quoted_unit_price", D("4.000000"))
    assert (item.quoted_unit_price, item.derived_field) == (D("3.50"), "")


def test_price_per_lb_comes_only_from_a_weight_that_was_entered():
    assert price_per_lb(line(amount=D("4.54"), net_weight=D("1000"), weight_unit="g")) == D("2.059309")
    assert price_per_lb(line(amount=D("4.54"), net_weight=D("2"), weight_unit="lb", derived_field="net_weight")) is None


def test_check_line_reports_every_problem_by_field():
    clean, errors = check_line({"description": " ", "quantity": "2", "amount": "1.234", "discount": "5",
                                "net_weight": "0", "weight_unit": "lb", "price_unit": "stone"})
    assert clean is None
    assert errors == {"description": ["此為必需欄位。"], "amount": ["小數最多 2 位。"], "price_unit": ["請選擇有效的單位。"],
                      "unit": ["有數字時請選擇單位。"], "net_weight": ["必須大於 0。"]}
    assert check_line({"description": "MILK", "amount": "3.00", "discount": "4"})[1] == {"discount": ["折扣不能超過原價。"]}
    assert check_line({"description": "MILK", "amount": "-1"})[1] == {"amount": ["必須大於或等於 0。"]}


def test_check_line_cleans_text_into_values():
    clean, errors = check_line({"description": "  BANANAS ", "net_weight": "2.85", "weight_unit": "lb",
                                "quoted_unit_price": "0.55", "price_unit": "lb", "amount": "1.57", "discount": ""})
    assert errors == {}
    assert clean == {"description": "BANANAS", "quantity": None, "unit": "", "amount": D("1.57"), "discount": D("0"),
                     "quoted_unit_price": D("0.55"), "price_unit": "lb", "net_weight": D("2.85"), "weight_unit": "lb",
                     "notes": ""}


@pytest.mark.parametrize("text, message", [("abc", "請輸入一個數字。"), ("1e3", None), ("NaN", "請輸入一個數字。"),
                                           ("12345678901", "小數點前最多 8 位。")])
def test_amounts_are_plain_decimals_within_the_column(text, message):
    errors = check_line({"description": "X", "amount": text})[1]
    assert errors.get("amount", [None]) == [message]


def test_tax_tip_and_discount_split_by_largest_remainder_and_add_up():
    expense = SimpleNamespace(amount=D("10.71"), tax=D("0.71"), tip=D("0"), receipt_discount=D("0"))
    lines = [SimpleNamespace(id=n, amount=D(a), discount=D("0")) for n, a in ((1, "3.33"), (2, "3.33"), (3, "3.34"))]
    result = breakdown(expense, lines)
    assert [result.shares[n].tax for n in (1, 2, 3)] == [24, 23, 24]
    assert sum(share.final for share in result.shares.values()) == 1071
    assert result.unrecorded == 0


def test_a_partly_itemized_receipt_shares_only_its_own_part_and_an_unknown_tax_stays_unknown():
    expense = SimpleNamespace(amount=D("20.00"), tax=None, tip=D("0"), receipt_discount=D("2.00"))
    result = breakdown(expense, [SimpleNamespace(id=1, amount=D("5.50"), discount=D("0.50"))])
    assert result.subtotal == 2200 and result.unrecorded == 1700
    share = result.shares[1]
    assert (share.net, share.tax, share.receipt_discount) == (500, None, 45)
    assert allocate(100, [1, 1, 1], 3) == [34, 33, 33]

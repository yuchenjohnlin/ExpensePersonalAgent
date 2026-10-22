"""The ledger's request bodies and their checks. Money and measures travel as strings ("12.30"),
never JSON numbers, so nothing passes through a float."""
import re
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, StrictBool

from .lines import parse_decimal

REQUIRED = "此為必需欄位。"


def _text(limit: int, required: bool):
    def check(value: str) -> str:
        value = value.strip()
        if required and not value:
            raise ValueError(REQUIRED)
        if len(value) > limit:
            raise ValueError(f"最多 {limit} 個字。")
        if "\x00" in value:
            raise ValueError("不允許空（null）字元。")
        return value
    return AfterValidator(check)


def _money(*, blank, positive: bool):
    """A money string with at most two decimals. blank is what null or "" means (REQUIRED: an error)."""
    def parse(value):
        if value is None or (isinstance(value, str) and not value.strip()):
            if blank is REQUIRED:
                raise ValueError(REQUIRED)
            return blank
        number = parse_decimal(value, 10, 2)
        if positive and number <= 0:
            raise ValueError("金額必須大於 0。")
        if number < 0:
            raise ValueError("金額不能是負數。")
        return number
    return BeforeValidator(parse)


DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def parse_day(value) -> date:
    if not isinstance(value, str) or not DAY.fullmatch(value):
        raise ValueError("請使用 YYYY-MM-DD 的日期。")
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise ValueError("請使用 YYYY-MM-DD 的日期。") from None
    if not 2000 <= day.year <= 2999:
        raise ValueError("請選擇 2000 至 2999 年的日期。")
    return day


Title = Annotated[str, _text(120, True)]
Merchant = Annotated[str, _text(120, False)]
Notes = Annotated[str, _text(500, False)]
Paid = Annotated[Decimal, _money(blank=REQUIRED, positive=True)]
Tax = Annotated[Decimal | None, _money(blank=None, positive=False)]  # null or "" = not known yet
Extra = Annotated[Decimal, _money(blank=Decimal("0.00"), positive=False)]  # null or "" = none
Day = Annotated[date, BeforeValidator(parse_day)]


class ExpenseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title
    amount: Paid
    date: Day
    category_id: int
    merchant: Merchant = ""
    notes: Notes = ""
    tax: Tax = None
    tip: Extra = Decimal("0.00")
    receipt_discount: Extra = Decimal("0.00")


class ExpensePatch(BaseModel):
    """Any subset; what is not sent stays. reviewed: true marks it looked at, false back to not."""
    model_config = ConfigDict(extra="forbid")
    title: Title | None = None
    amount: Paid | None = None
    date: Day | None = None
    category_id: int | None = None
    merchant: Merchant | None = None
    notes: Notes | None = None
    tax: Tax = None
    tip: Extra | None = None
    receipt_discount: Extra | None = None
    total_only: StrictBool | None = None
    reviewed: StrictBool | None = None


LineText = str | None


class LineIn(BaseModel):
    """A line's fields as text (null or "" for unknown); checked together by lines.check_line."""
    model_config = ConfigDict(extra="forbid")
    description: LineText = None
    quantity: LineText = None
    unit: LineText = None
    amount: LineText = None
    discount: LineText = None
    quoted_unit_price: LineText = None
    price_unit: LineText = None
    net_weight: LineText = None
    weight_unit: LineText = None
    notes: LineText = None


class LinePatch(LineIn):
    """Any subset of a line's fields; the rest stay."""

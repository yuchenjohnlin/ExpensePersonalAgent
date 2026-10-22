"""From a reading to an expense: what the header and lines would be, and whether posting may happen
without anyone looking (pm/decisions/reading-auto-post-when-checks-pass.md).

The automatic post needs: a merchant, a date and a total read; the server's arithmetic checks all
passing; a date not in the future; money the ledger can hold; and no expense already on that day
with the same merchant and total (a likely duplicate). Anything else goes to "needs a look" with
the reasons. Passing does not prove the reading right, which is why every auto-posted expense
stays unreviewed until looked at.
"""
from datetime import date
from decimal import Decimal, InvalidOperation

UNREAD_ITEM = "（未讀出品項）"
NEGATIVE = "負數（折價），請在折扣欄補上"


def money(text) -> Decimal | None:
    """A read amount as ledger money (two places); None for unknown; ValueError if it cannot be."""
    if text is None:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise ValueError(text) from None
    if number.as_tuple().exponent < -2 or abs(number) >= Decimal("100000000"):
        raise ValueError(text)
    return number.quantize(Decimal("0.01"))


def line_values(item: dict) -> dict:
    """A read item as a line's fields (the reading uses the same names). Only an unprinted unit gets a
    default: a receipt's "2 @ 3.49" counts scanned items, so a count or price without a unit is per
    each, unless the line is sold by weight."""
    quantity, price, weight = item.get("quantity"), item.get("quoted_unit_price"), item.get("net_weight")
    weight_unit = item.get("weight_unit") or ""
    return {"description": (item.get("description") or UNREAD_ITEM)[:255], "amount": item.get("amount"),
            "discount": item.get("discount") or "0",
            "quantity": quantity, "unit": item.get("unit") or ("each" if quantity is not None else ""),
            "quoted_unit_price": price,
            "price_unit": item.get("price_unit") or (
                "" if price is None else weight_unit if weight is not None and weight_unit else "each"),
            "net_weight": weight, "weight_unit": weight_unit, "notes": ""}


def lines_from(result: dict, check_line) -> tuple[list[tuple[int, dict]], list[dict]]:
    """((item index, clean line values) for each item that can be a line, skipped items with why).
    check_line is the ledger's: values -> (clean or None, reason)."""
    lines, skipped = [], []
    for index, item in enumerate(result["items"], 1):
        values = line_values(item)
        amount = item.get("amount")
        if amount is not None and Decimal(amount) < 0:
            skipped.append({"index": index, "description": values["description"], "amount": amount, "reason": NEGATIVE})
            continue
        clean, reason = check_line(values)
        if reason:
            skipped.append({"index": index, "description": values["description"], "amount": amount, "reason": reason})
            continue
        lines.append((index, clean))
    return lines, skipped


def header_from(result: dict, today: date) -> tuple[dict | None, list[str]]:
    """(the expense header to post, []) or (None, why it cannot be posted automatically). The header
    has no category yet; the caller gives it 未分類."""
    reasons = []
    missing = [label for key, label in (("merchant", "店家"), ("date", "日期"), ("amount", "總額"))
               if not (result.get(key) or "").strip()]
    if missing:
        reasons.append(f"讀不到{'、'.join(missing)}。")
    try:
        amount, tax, tip, discount = (money(result.get(key)) for key in ("amount", "tax", "tip", "receipt_discount"))
    except ValueError:
        return None, reasons + ["讀到的金額不是兩位小數的金額。"]
    if amount is not None and amount <= 0:
        reasons.append("讀到的總額不是正數。")
    day = date.fromisoformat(result["date"]) if result.get("date") else None
    if day is not None and day > today:
        reasons.append("讀到的日期在未來。")
    if reasons:
        return None, reasons
    merchant = result["merchant"].strip()[:120]
    return {"title": merchant, "amount": amount, "date": day, "merchant": merchant, "notes": "",
            "tax": tax, "tip": tip or Decimal("0.00"),
            "receipt_discount": abs(discount) if discount is not None else Decimal("0.00")}, []

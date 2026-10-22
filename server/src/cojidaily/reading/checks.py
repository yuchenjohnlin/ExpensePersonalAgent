"""The server's own arithmetic checks on a reading (moved from api/app/reading.py arithmetic_warnings).

Not stored with the reading: worked out whenever a reading is used, so a changed rule applies to
old readings too. A difference within $0.02 is not reported. Passing them does not prove a reading
right (a wrong date or merchant passes), which is why posting adds its own checks.
"""
import re
from decimal import Decimal

from ..platform.units import GRAMS_PER_UNIT

NUMBER_PATTERN = r"^-?(?:0|[1-9][0-9]{0,14})(?:\.[0-9]{1,6})?$"
DECIMAL_RE = re.compile(NUMBER_PATTERN)
TOLERANCE = Decimal("0.02")


def decimal_value(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 24 or not DECIMAL_RE.fullmatch(value):
        raise ValueError("invalid decimal string")
    parsed = Decimal(value)
    if not parsed.is_finite():
        raise ValueError("nonfinite decimal")
    return parsed


def priced_measure(item):
    """How much of the item its unit price is quoted for: the weight in the price's mass unit, or
    the count when the price is per the same (or an unprinted) unit."""
    price_unit = item["price_unit"]
    weight = decimal_value(item["net_weight"])
    if weight is not None and price_unit in GRAMS_PER_UNIT:
        weight_unit = item["weight_unit"] or price_unit
        return weight * GRAMS_PER_UNIT[weight_unit] / GRAMS_PER_UNIT[price_unit]
    quantity = decimal_value(item["quantity"])
    if quantity is not None and price_unit in (None, item["unit"]):
        return quantity
    return None


def arithmetic_warnings(result) -> list[str]:
    """Three checks: each line's measure x unit price against its amount; the items against the
    subtotal (before or after their own discounts); subtotal + tax + tip - discount against the total."""
    notes = []
    items = result["items"]
    subtotal = decimal_value(result["subtotal"])
    amounts = [decimal_value(item["amount"]) for item in items]
    if items and subtotal is not None and None not in amounts:
        listed = sum(amounts, Decimal(0))
        net = listed - sum((decimal_value(item["discount"]) or Decimal(0) for item in items), Decimal(0))
        # Receipts differ on whether the subtotal is before or after item savings.
        if min(abs(listed - subtotal), abs(net - subtotal)) > TOLERANCE:
            notes.append("品項金額加總與小計不一致；可能有漏讀、重複或折扣，請核對原照。")
    for index, item in enumerate(items, 1):
        measure = priced_measure(item)
        price = decimal_value(item["quoted_unit_price"])
        amount = decimal_value(item["amount"])
        if None not in (measure, price, amount):
            if abs(measure * price - amount) > TOLERANCE:
                notes.append(f"第 {index} 項的數量或淨重乘單價與該行金額不一致，請核對計價方式。")
    tax, tip, discount, total = [decimal_value(result[key]) for key in ("tax", "tip", "receipt_discount", "amount")]
    if None not in (subtotal, tax, total):
        expected = subtotal + tax + (tip or 0) - abs(discount or 0)
        if abs(expected - total) > TOLERANCE:
            notes.append("小計加稅與小費、減整張折扣，與總額不一致；未自動修改任何讀取值。")
    return notes

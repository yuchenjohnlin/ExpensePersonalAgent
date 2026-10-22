"""A line's checks and its derived measure (from api/app/lines.py, i.e. backend/'s PurchaseLineForm and
PurchaseLine.fill_derived), without the Django form wording api/ had to keep.

amount = measure x unit price: when the line has a positive amount and one side, the server fills
the other and marks it in derived_field (pm/decisions/derive-measure-from-amount.md). Weight pairs
with a per-mass price; count and volume pair with a quantity in the same unit as the price. A value
the user typed is never changed.
"""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from ..platform.units import GRAMS_PER_UNIT, UNITS, WEIGHT_UNITS

SIX_PLACES = Decimal("0.000001")
LARGEST_MEASURE = Decimal("9999999999.999999")  # NUMERIC(16,6)
FIELDS = ("description", "quantity", "unit", "amount", "discount", "quoted_unit_price", "price_unit", "net_weight",
          "weight_unit", "notes")
# max digits, decimal places, smallest allowed, whether the smallest is excluded
DECIMALS = {"quantity": (16, 6, Decimal("0"), False), "amount": (10, 2, Decimal("0"), False),
            "discount": (10, 2, Decimal("0"), False), "quoted_unit_price": (16, 6, Decimal("0"), False),
            "net_weight": (16, 6, Decimal("0"), True)}
CHOICES = {"unit": UNITS, "price_unit": UNITS, "weight_unit": WEIGHT_UNITS}
TEXTS = {"description": (255, True), "notes": (500, False)}
PAIRS = (("quantity", "unit"), ("quoted_unit_price", "price_unit"), ("net_weight", "weight_unit"))


def parse_decimal(text, max_digits: int, places: int) -> Decimal | None:
    """A plain decimal string (or None / "" for unknown) within NUMERIC(max_digits, places); raises ValueError."""
    if text is None or (isinstance(text, str) and not text.strip()):
        return None
    if isinstance(text, Decimal):  # already clean (a module passing check_line's output on)
        number = text
    elif not isinstance(text, str):
        raise ValueError("請以文字填寫數字。")
    else:
        try:
            number = Decimal(text.strip())
        except InvalidOperation:
            raise ValueError("請輸入一個數字。") from None
    if not number.is_finite():
        raise ValueError("請輸入一個數字。")
    exponent = number.as_tuple().exponent
    if -exponent > places:
        raise ValueError(f"小數最多 {places} 位。")
    if abs(number) >= Decimal(10) ** (max_digits - places):
        raise ValueError(f"小數點前最多 {max_digits - places} 位。")
    return number


def check_line(values: dict) -> tuple[dict | None, dict[str, list[str]]]:
    """A whole line's values (text or None) -> (clean values, {}) or (None, errors by field)."""
    errors: dict[str, list[str]] = {}
    data = {}

    def add(name, message):
        errors.setdefault(name, []).append(message)

    for name in FIELDS:
        raw = values.get(name)
        if name in DECIMALS:
            places = DECIMALS[name]
            try:
                data[name] = parse_decimal(raw, places[0], places[1])
            except ValueError as error:
                add(name, str(error))
        elif name in CHOICES:
            text = raw or ""
            if not isinstance(text, str) or (text and text not in CHOICES[name]):
                add(name, "請選擇有效的單位。")
            data[name] = text if isinstance(text, str) else ""
        else:
            limit, required = TEXTS[name]
            text = (raw or "").strip() if isinstance(raw, str) or raw is None else None
            if text is None:
                add(name, "請使用文字。")
            elif required and not text:
                add(name, "此為必需欄位。")
            elif len(text) > limit:
                add(name, f"最多 {limit} 個字。")
            data[name] = text or ""
    for number, unit in PAIRS:
        if data.get(number) is not None and not data.get(unit) and unit not in errors:
            add(unit, "有數字時請選擇單位。")
    for name, (_, _, smallest, exclusive) in DECIMALS.items():
        value = data.get(name)
        if name not in errors and value is not None and (value < smallest or (exclusive and value == smallest)):
            add(name, f"必須大於 {smallest}。" if exclusive else f"必須大於或等於 {smallest}。")
    # The discount against the price, once both are good numbers.
    if "discount" not in errors and "amount" not in errors:
        discount = data.get("discount") or Decimal("0")
        if discount and data.get("amount") is None:
            add("discount", "有折扣時請填原價。")
        elif data.get("amount") is not None and discount > data["amount"]:
            add("discount", "折扣不能超過原價。")
        data["discount"] = discount
    return (None, errors) if errors else (data, {})


def fill_derived(line, previous_field: str = "", previous_value=None) -> None:
    """Fill the blank side of amount = measure x unit price from what was entered.

    previous_field / previous_value: what the server had derived before this edit. If it still holds
    that value the user did not change it, so it is cleared and worked out again from the new figures.
    """
    if previous_field and getattr(line, previous_field) == previous_value:
        setattr(line, previous_field, None)
    line.derived_field = ""
    amount, price = line.amount, line.quoted_unit_price
    if amount is None or amount <= 0:
        return
    if price is not None:
        if price <= 0:
            return
        if line.price_unit in GRAMS_PER_UNIT and line.net_weight is None:
            unit = line.weight_unit or line.price_unit
            weight = amount / price * GRAMS_PER_UNIT[line.price_unit] / GRAMS_PER_UNIT[unit]
            _set_derived(line, "net_weight", weight, "weight_unit", unit)
        elif line.price_unit and line.price_unit not in GRAMS_PER_UNIT and line.quantity is None \
                and line.unit in ("", line.price_unit):
            _set_derived(line, "quantity", amount / price, "unit", line.price_unit)
        return
    # Without a chosen price unit, weight wins over a count.
    if line.net_weight is not None and line.weight_unit and line.price_unit in ("", *GRAMS_PER_UNIT):
        unit = line.price_unit or line.weight_unit
        weight = line.net_weight * GRAMS_PER_UNIT[line.weight_unit] / GRAMS_PER_UNIT[unit]
        _set_derived(line, "quoted_unit_price", amount / weight, "price_unit", unit)
    elif line.quantity and line.unit and line.unit not in GRAMS_PER_UNIT and line.price_unit in ("", line.unit):
        _set_derived(line, "quoted_unit_price", amount / line.quantity, "price_unit", line.unit)


def _set_derived(line, field, value, unit_field, unit) -> None:
    value = value.quantize(SIX_PLACES, rounding=ROUND_HALF_UP)
    if value <= 0 or value > LARGEST_MEASURE:
        return  # Not storable; leave the field unknown rather than wrong.
    setattr(line, field, value)
    setattr(line, unit_field, unit)
    line.derived_field = field


def price_per_lb(line) -> Decimal | None:
    """The line's price per pound from its own amount and weight; None when the weight was derived
    from the unit price (it would only echo that price back)."""
    if line.amount is None or line.net_weight is None or line.derived_field == "net_weight":
        return None
    factor = GRAMS_PER_UNIT.get(line.weight_unit)
    if not factor or line.net_weight <= 0:
        return None
    pounds = line.net_weight * factor / GRAMS_PER_UNIT["lb"]
    return (line.amount / pounds).quantize(SIX_PLACES, rounding=ROUND_HALF_UP)

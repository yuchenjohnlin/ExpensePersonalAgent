"""Each line's share of what a receipt adds or takes off as a whole (moved from api/app/adjustments.py,
itself backend/'s code; only the relationship name changed).

The receipt's printed tax, tip and whole-receipt discount are the facts; a line's part of them is
worked out on reading and never stored. Each is a fraction of the receipt's pre-tax subtotal, and
the subtotal comes from the paid total (paid - tax - tip + receipt discount), not from the lines
entered. Cents are handed out by largest remainder, with the unrecorded rest as one more claimant,
so a fully itemized receipt's parts add up to exactly what it printed.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

RATE_PLACES = Decimal("0.000001")


def cents(value: Decimal) -> int:
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass
class LineShare:
    net: int  # cents: the line's price less its own discount
    tax: int | None  # None while the receipt's tax is unknown
    receipt_discount: int
    tip: int

    @property
    def final(self) -> int:
        return self.net + (self.tax or 0) - self.receipt_discount + self.tip


@dataclass
class Breakdown:
    subtotal: int  # cents before tax, after item discounts, before the receipt discount
    net_total: int  # the recorded lines with a known price
    shares: dict  # line id -> LineShare; lines with an unknown price are absent
    tax: int | None
    tip: int
    receipt_discount: int

    @property
    def unrecorded(self) -> int:
        # Items not entered yet (or a mistyped figure); zero when the receipt is fully itemized.
        return self.subtotal - self.net_total

    def rate(self, part):
        if part is None or self.subtotal <= 0:
            return None
        return (Decimal(part) / Decimal(self.subtotal)).quantize(RATE_PLACES, rounding=ROUND_HALF_UP)


def subtotal_cents(paid, tax, tip, receipt_discount) -> int:
    return cents(paid) - cents(tax or Decimal("0")) - cents(tip) + cents(receipt_discount)


def allocate(total: int, weights: list[int], whole: int) -> list[int]:
    """Split total cents in proportion to weights out of whole; the gap up to whole keeps its own part."""
    if total == 0 or whole <= 0:
        return [0] * len(weights)
    claims = [*weights, whole - sum(weights)]
    exact = [divmod(total * weight, whole) for weight in claims]
    parts = [part for part, _ in exact]
    short = total - sum(parts)
    # Ties go to the earlier line, so the result depends on nothing but the receipt order.
    for index in sorted(range(len(claims)), key=lambda i: (-exact[i][1], i))[:short]:
        parts[index] += 1
    return parts[:-1]


def breakdown(expense, lines) -> Breakdown:
    lines = [line for line in lines if line.amount is not None]
    nets = [cents(line.amount) - cents(line.discount) for line in lines]
    tax = None if expense.tax is None else cents(expense.tax)
    tip, receipt_discount = cents(expense.tip), cents(expense.receipt_discount)
    subtotal = subtotal_cents(expense.amount, expense.tax, expense.tip, expense.receipt_discount)
    net_total = sum(nets)
    # Items adding up to more than the receipt's subtotal means a figure is off; share among them alone.
    whole = max(subtotal, net_total)
    taxes = [None] * len(lines) if tax is None else allocate(tax, nets, whole)
    discounts, tips = allocate(receipt_discount, nets, whole), allocate(tip, nets, whole)
    shares = {line.id: LineShare(net, part_tax, part_discount, part_tip)
              for line, net, part_tax, part_discount, part_tip in zip(lines, nets, taxes, discounts, tips)}
    return Breakdown(subtotal, net_total, shares, tax, tip, receipt_discount)

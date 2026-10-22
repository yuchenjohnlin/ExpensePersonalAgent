/** Money is stored as printed; a percentage or a discounted price is only a way to type it. These
 * turn what was typed into the money the server stores, in cents to avoid float drift (moved from
 * the old frontend's receipt-math.ts). */
import { ApiError } from "@/shared/api/client";

const MONEY = /^\$?\s*(\d+)(?:\.(\d{1,2}))?$/;
const PERCENT = /^(\d+(?:\.\d+)?)\s*%$/;

export const toCents = (text: string): number | null => {
  const match = MONEY.exec(text.trim());
  return match ? Number(match[1]) * 100 + Number((match[2] ?? "").padEnd(2, "0")) : null;
};
export const fromCents = (cents: number) => (cents / 100).toFixed(2);
export const toFraction = (text: string): number | null => {
  const match = PERCENT.exec(text.trim());
  return match ? Number(match[1]) / 100 : null;
};
/** 0.030096 -> "3.01%" */
export const percentText = (rate: string | null) =>
  rate === null ? "" : `${(Number(rate) * 100).toFixed(2).replace(/\.?0+$/, "")}%`;

const fail = (field: string, message: string): never => {
  throw new ApiError(400, { error: "請檢查輸入內容。", fields: { [field]: [message] } });
};
const money = (text: string, field: string, label: string) => toCents(text) ?? fail(field, `${label}請填金額，例如 4.69。`);

/** A receipt line typed one of the ways receipts print it: price and discount (Costco), the
 * discounted price and what was saved (H Mart), or a percentage off. Returns the price before the
 * discount and the discount, as the server stores them. */
export function resolveLine({ amount, discount, net }: { amount: string; discount: string; net: string }) {
  const a = amount.trim(), d = discount.trim(), n = net.trim();
  const off = toFraction(d);
  if (off !== null && !(off < 1)) fail("discount", "折扣要小於 100%。");
  if (!n) {
    if (off === null) return { amount: a || null, discount: d || null };
    if (!a) fail("discount", "折扣用 % 時，請填原價或折後價。");
    const price = money(a, "amount", "原價");
    return { amount: a, discount: fromCents(Math.round(price * off)) };
  }
  const paid = money(n, "net", "折後價");
  let price: number;
  if (off !== null) price = Math.round(paid / (1 - off));
  else if (d) price = paid + money(d, "discount", "折扣");
  else if (a) price = money(a, "amount", "原價");
  else price = paid;
  if (price < paid) fail("net", "折後價不能高於原價。");
  return { amount: fromCents(price), discount: fromCents(price - paid) };
}

export type Adjustments = { tax: string | null; tip: string; receipt_discount: string };

/** The receipt's tax, tip and whole-receipt discount. Tax is copied as printed (blank: unknown); tip
 * and discount may be a percentage of the pre-tax subtotal, which itself depends on them:
 * subtotal x (1 + tip% - discount%) = paid - tax - fixed tip + fixed discount. */
export function resolveAdjustments(paid: string, typed: Record<keyof Adjustments, string>): Adjustments {
  const tax = typed.tax.trim();
  if (toFraction(tax) !== null) fail("tax", "稅請照收據填金額。");
  const taxCents = tax ? money(tax, "tax", "稅") : 0;
  const tipRate = toFraction(typed.tip), discountRate = toFraction(typed.receipt_discount);
  if (discountRate !== null && !(discountRate < 1)) fail("receipt_discount", "折扣要小於 100%。");
  const fixed = (text: string, rate: number | null, field: string, label: string) =>
    rate !== null || !text.trim() ? 0 : money(text, field, label);
  const tip = fixed(typed.tip, tipRate, "tip", "小費");
  const off = fixed(typed.receipt_discount, discountRate, "receipt_discount", "折扣");
  const subtotal = ((toCents(paid) ?? 0) - taxCents - tip + off) / (1 + (tipRate ?? 0) - (discountRate ?? 0));
  return {
    tax: tax ? fromCents(taxCents) : null,
    tip: fromCents(tipRate === null ? tip : Math.round(subtotal * tipRate)),
    receipt_discount: fromCents(discountRate === null ? off : Math.round(subtotal * discountRate)),
  };
}

// The shapes the server's ledger answers (server/README.md, "The ledger"). Money is a string.

export type Category = { id: number; name: string; system: boolean };

export type Expense = {
  id: number;
  title: string;
  amount: string;
  date: string;
  category: { id: number; name: string };
  merchant: string;
  notes: string;
  tax: string | null; // null: not read off the receipt yet
  tip: string;
  receipt_discount: string;
  total_only: boolean;
  reviewed_at: string | null; // null: posted automatically, not looked at yet
  line_count: number;
  created_at: string;
  updated_at: string;
};

export type Line = {
  id: number;
  expense_id: number;
  description: string;
  quantity: string | null;
  unit: string;
  amount: string | null;
  discount: string;
  quoted_unit_price: string | null;
  price_unit: string;
  net_weight: string | null;
  weight_unit: string;
  notes: string;
  // Which value the server worked out from amount = measure x unit price ("" for none).
  derived_field: "" | "quantity" | "quoted_unit_price" | "net_weight";
  price_per_lb: string | null;
  net_amount: string | null;
  tax_share: string | null;
  discount_share: string | null;
  tip_share: string | null;
  final_amount: string | null;
};

export type Summary = {
  paid_total: string;
  line_total: string;
  line_discount_total: string;
  net_total: string;
  subtotal: string;
  tax_rate: string | null;
  tip_rate: string | null;
  receipt_discount_rate: string | null;
  unrecorded: string; // what the lines leave unexplained; "0.00" when fully itemized
  unknown_amount_count: number;
};

export type ExpenseDetail = Expense & { lines: Line[]; summary: Summary };

export type MonthDay = { date: string; total: string; count: number; merchants: string[] };
export type Month = { month: string; today: string; total: string; days: MonthDay[] };
export type Day = { date: string; total: string; expenses: ExpenseDetail[] };

export type ExpenseInput = {
  title: string;
  amount: string;
  date: string;
  category_id: number;
  merchant?: string;
  notes?: string;
  tax?: string | null;
  tip?: string | null;
  receipt_discount?: string | null;
};

export type ExpenseChanges = Partial<ExpenseInput> & { total_only?: boolean; reviewed?: boolean };

export type LineFields = Partial<Record<
  "description" | "quantity" | "unit" | "amount" | "discount" | "quoted_unit_price" | "price_unit" | "net_weight"
  | "weight_unit" | "notes", string | null>>;

export const UNITS = ["each", "pack", "g", "kg", "lb", "oz", "fl_oz", "mL", "L", "gal"] as const;
export const WEIGHT_UNITS = ["g", "kg", "lb", "oz"] as const;
export const UNIT_LABELS: Record<string, string> = {
  each: "個", pack: "包", g: "g", kg: "kg", lb: "lb", oz: "oz", fl_oz: "fl oz", mL: "mL", L: "L", gal: "gal",
};

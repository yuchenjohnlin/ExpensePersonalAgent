/** An expense's lines as one table you edit in place, with the receipt's own totals under it (the
 * old frontend's ExpenseLines, pm/decisions/inline-grid-autosave.md). */
import { useQueryClient } from "@tanstack/react-query";
import { Trash2Icon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type * as React from "react";

import { api } from "@/shared/api/client";
import { measure, money } from "@/shared/lib/format";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { GridCell, RowError, RowState, useGridRow, useReportRisk, type GridRow } from "@/shared/ui/grid";

import { expenseChanged } from "./api";
import { percentText, resolveAdjustments, resolveLine } from "./receipt-math";
import type { ExpenseDetail, Line, LineFields } from "./types";
import { UNIT_LABELS, UNITS, WEIGHT_UNITS } from "./types";

type LineDraft = {
  // net is only typed (a receipt printing the discounted price); the server keeps price and discount.
  description: string; amount: string; discount: string; net: string; quantity: string; unit: string;
  quoted_unit_price: string; price_unit: string; net_weight: string; weight_unit: string;
};
type Measure = "quantity" | "quoted_unit_price" | "net_weight";

const LABELS: Record<string, string> = {
  description: "收據原文", amount: "原價", discount: "折扣", net: "折後", quantity: "數量", unit: "數量單位",
  quoted_unit_price: "單價", price_unit: "計價單位", net_weight: "淨重", weight_unit: "重量單位",
};
const BLANK: LineDraft = { description: "", amount: "", discount: "", net: "", quantity: "", unit: "",
  quoted_unit_price: "", price_unit: "", net_weight: "", weight_unit: "" };
const COLUMNS = 9;

// A value the server worked out starts blank, so saving works it out again from what changed.
const entered = (line: Line, field: Measure) => (line[field] === null || line.derived_field === field ? "" : measure(line[field]));
const toDraft = (line: Line): LineDraft => ({
  description: line.description, amount: line.amount ?? "", discount: Number(line.discount) ? line.discount : "", net: "",
  quantity: entered(line, "quantity"), unit: line.unit, quoted_unit_price: entered(line, "quoted_unit_price"),
  price_unit: line.price_unit, net_weight: entered(line, "net_weight"), weight_unit: line.weight_unit,
});
const toFields = (draft: LineDraft): LineFields => ({
  description: draft.description, ...resolveLine(draft),
  quantity: draft.quantity.trim() || null, unit: draft.unit,
  quoted_unit_price: draft.quoted_unit_price.trim() || null, price_unit: draft.price_unit,
  net_weight: draft.net_weight.trim() || null, weight_unit: draft.weight_unit,
});
// What the server worked out, greyed in the empty cell it fills.
const derivedHint = (line: Line | null, field: Measure) => {
  const value = line?.[field];
  if (!line || line.derived_field !== field || value === null || value === undefined) return "";
  return `≈ ${field === "quoted_unit_price" ? Number(value).toFixed(2) : Number(value).toFixed(2).replace(/\.?0+$/, "")}`;
};
const netHint = (line: Line | null) => (line?.net_amount && Number(line.discount) ? `≈ ${line.net_amount}` : "");

export type GridEvents = {
  report: (key: string, atRisk: boolean) => void;
  onLost: (message: string) => void;
};

function useLineSave() {
  const client = useQueryClient();
  return async (write: Promise<ExpenseDetail>) => {
    const expense = await write;
    expenseChanged(client, expense);
    return expense;
  };
}

function UnitChoice({ value, label, units, onChange, disabled }: {
  value: string; label: string; units: readonly string[]; onChange: (value: string) => void; disabled?: boolean;
}) {
  return (
    <select aria-label={label} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
      <option value="" />
      {units.map((unit) => <option key={unit} value={unit}>{UNIT_LABELS[unit]}</option>)}
    </select>
  );
}

function LineCells({ row, line, label, disabled, firstRef }: {
  row: GridRow<LineDraft>; line: Line | null; label: string; disabled?: boolean; firstRef?: React.Ref<HTMLInputElement>;
}) {
  const input = (key: keyof LineDraft, placeholder: string, extra: React.ComponentProps<"input"> = {}) => (
    <input aria-label={`${LABELS[key]}，${label}`} value={row.value[key]} disabled={disabled} placeholder={placeholder}
      aria-invalid={Boolean(row.fields[key]) || undefined} onChange={(event) => row.set(key, event.target.value)} {...extra} />
  );
  const amount = (key: Measure) => {
    const hint = derivedHint(line, key);
    return input(key, hint || "—", { inputMode: "decimal", className: hint ? "derived" : undefined,
      title: hint ? "推算值；填了就以你填的為準，清空會重新推算" : undefined });
  };
  const unit = (key: "unit" | "price_unit" | "weight_unit", units: readonly string[]) => (
    <UnitChoice value={row.value[key]} label={`${LABELS[key]}，${label}`} units={units} disabled={disabled}
      onChange={(text) => row.set(key, text)} />
  );
  const right = "[&_input]:text-right [&_input]:tabular-nums";
  return (
    <>
      <td>
        <GridCell row={row} keys={["description"]} className="[&_input]:font-medium">
          {input("description", line ? "" : "＋ 新增品項：收據原文", { maxLength: 255, ref: firstRef })}
        </GridCell>
      </td>
      <td><GridCell row={row} keys={["amount"]} className={right}>{input("amount", line ? "未知" : "", { inputMode: "decimal" })}</GridCell></td>
      <td><GridCell row={row} keys={["discount"]} className={right}>{input("discount", "—", { title: "收據上這項省了多少，可填 2 或 20%" })}</GridCell></td>
      <td>
        <GridCell row={row} keys={["net"]} className={right}>
          {input("net", netHint(line) || "—", { inputMode: "decimal", className: netHint(line) ? "derived" : undefined,
            title: "收據只印折後價時填這裡，原價＝折後＋折扣" })}
        </GridCell>
      </td>
      <td className="money text-right whitespace-nowrap">{line ? <FinalCell line={line} /> : null}</td>
      <td><GridCell row={row} keys={["quantity", "unit"]} className={right}>{amount("quantity")}{unit("unit", UNITS)}</GridCell></td>
      <td><GridCell row={row} keys={["net_weight", "weight_unit"]} className={right}>{amount("net_weight")}{unit("weight_unit", WEIGHT_UNITS)}</GridCell></td>
      <td>
        <GridCell row={row} keys={["quoted_unit_price", "price_unit"]} className={right}>
          {amount("quoted_unit_price")}<span className="text-muted-foreground">/</span>{unit("price_unit", UNITS)}
        </GridCell>
      </td>
    </>
  );
}

/** What the item came to with its part of the receipt's tax, tip and discount. */
function FinalCell({ line }: { line: Line }) {
  if (line.final_amount === null) return null;
  const parts = [line.tax_share === null ? "稅未填" : `稅 +${line.tax_share}`,
    Number(line.discount_share) ? `整張折扣 −${line.discount_share}` : "", Number(line.tip_share) ? `小費 +${line.tip_share}` : ""];
  return (
    <span className="text-muted-foreground block px-2 py-1.5" title={parts.filter(Boolean).join(" · ")}>
      {money(line.final_amount)}
      {line.tax_share === null ? <small className="block text-[10px]">未含稅</small> : null}
    </span>
  );
}

function LineRow({ line, events }: { line: Line; events: GridEvents }) {
  const save = useLineSave();
  const [deleting, setDeleting] = useState(false);
  const row = useGridRow(toDraft(line), async (draft) => {
    const expense = await save(api.patch<ExpenseDetail>(`/api/lines/${line.id}`, toFields(draft)));
    const stored = expense.lines.find((other) => other.id === line.id);
    return stored ? toDraft(stored) : undefined;
  }, { onLost: (message) => events.onLost(`「${line.description}」的修改沒有存成功：${message}`) });
  useReportRisk(events.report, `${line.expense_id}:${line.id}`, row.atRisk);
  return (
    <>
      <tr className="border-t border-dashed">
        <LineCells row={row} line={line} label={line.description} />
        <td className="px-1 text-right whitespace-nowrap">
          <RowState row={row} name={line.description} />
          <Button variant="ghost" size="icon-sm" aria-label={`刪除品項 ${line.description}`} onClick={() => setDeleting(true)}>
            <Trash2Icon className="text-muted-foreground" />
          </Button>
          <ConfirmDialog open={deleting} onOpenChange={setDeleting} destructive title={`刪除「${line.description}」？`}
            confirmLabel="刪除" description="這個品項會從這筆支出移除，不能復原。"
            onConfirm={() => { setDeleting(false); void save(api.delete<ExpenseDetail>(`/api/lines/${line.id}`)); }} />
        </td>
      </tr>
      <RowError row={row} labels={LABELS} colSpan={COLUMNS} />
    </>
  );
}

function NewLineRow({ expense, label, events }: { expense: ExpenseDetail; label: string; events: GridEvents }) {
  const save = useLineSave();
  const first = useRef<HTMLInputElement>(null);
  const next = useRef(false);
  const row = useGridRow(BLANK, async (draft) => {
    await save(api.post<ExpenseDetail>(`/api/expenses/${expense.id}/lines`, { ...toFields(draft), notes: "" }));
    next.current = true;
  }, { create: true });
  useReportRisk(events.report, `${expense.id}:new`, row.atRisk);
  const saving = row.status === "saving";
  useEffect(() => { // keep going: after adding, the cursor waits in the next new line
    if (!saving && next.current) {
      next.current = false;
      first.current?.focus();
    }
  }, [saving]);
  return (
    <>
      <tr className="border-t">
        <LineCells row={row} line={null} label={`新增品項 ${label}`} disabled={saving} firstRef={first} />
        <td className="px-1 text-right whitespace-nowrap"><RowState row={row} name={`品項 ${label}`} /></td>
      </tr>
      <RowError row={row} labels={LABELS} colSpan={COLUMNS} />
    </>
  );
}

const ADJUSTMENT_LABELS: Record<string, string> = { tax: "稅", tip: "小費", receipt_discount: "整張折扣" };
type AdjustmentDraft = { tax: string; tip: string; receipt_discount: string };
const blankZero = (value: string) => (Number(value) ? value : "");
const toAdjustments = (expense: ExpenseDetail): AdjustmentDraft =>
  ({ tax: expense.tax ?? "", tip: blankZero(expense.tip), receipt_discount: blankZero(expense.receipt_discount) });

/** The receipt's own lines under the items: tax as printed, tip and whole-receipt discount in money
 * or %, checked against what was paid. */
function ReceiptTotals({ expense, events }: { expense: ExpenseDetail; events: GridEvents }) {
  const save = useLineSave();
  const { summary } = expense;
  const name = expense.merchant || expense.title;
  const row = useGridRow(toAdjustments(expense), async (draft) =>
    toAdjustments(await save(api.patch<ExpenseDetail>(`/api/expenses/${expense.id}`, resolveAdjustments(expense.amount, draft)))),
  { onLost: (message) => events.onLost(`「${name}」的稅、小費或折扣沒有存成功：${message}`) });
  useReportRisk(events.report, `${expense.id}:totals`, row.atRisk);
  const count = expense.lines.length;
  const field = (key: keyof AdjustmentDraft, placeholder: string, rate: string | null, sign: string) => (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-muted-foreground">{ADJUSTMENT_LABELS[key]}{rate !== null && Number(rate) > 0 ? <small className="ml-1">{percentText(rate)}</small> : null}</dt>
      <dd>
        <GridCell row={row} keys={[key]} className="w-32 [&_input]:text-right [&_input]:tabular-nums">
          <span aria-hidden className="text-muted-foreground pl-2">{sign}</span>
          <input aria-label={`${ADJUSTMENT_LABELS[key]}，${name}`} value={row.value[key]} placeholder={placeholder} inputMode="decimal"
            aria-invalid={Boolean(row.fields[key]) || undefined} onChange={(event) => row.set(key, event.target.value)} />
        </GridCell>
      </dd>
    </div>
  );
  const gap = Number(summary.unrecorded);
  return (
    <div className="grid gap-1">
      <dl className="ml-auto grid w-full max-w-sm gap-0.5 text-sm">
        {count > 0 ? <Line label="原價合計" value={money(summary.line_total)} /> : null}
        {Number(summary.line_discount_total) > 0 ? <Line label="品項折扣" value={`−${money(summary.line_discount_total)}`} /> : null}
        {field("receipt_discount", "0 或 5%", summary.receipt_discount_rate, "−")}
        {field("tax", "照收據填", summary.tax_rate, "+")}
        {field("tip", "0 或 18%", summary.tip_rate, "+")}
        {count > 0 ? (gap === 0 && !summary.unknown_amount_count
          ? <Line label="核對" value="✓ 剛好等於實付" tone="text-success-foreground" />
          : <Line label={expense.tax === null ? "未記品項與稅" : "未記品項"} value={`${gap > 0 ? "+" : ""}${money(summary.unrecorded)}`} />)
          : null}
        <div className="flex items-center justify-between gap-3 border-t pt-1 font-medium">
          <dt className="flex items-center gap-2">實付 <RowState row={row} name={`稅、小費與折扣 ${name}`} /></dt>
          <dd className="money pr-2">{money(summary.paid_total)}</dd>
        </div>
      </dl>
      {row.status === "error" ? (
        <p role="alert" className="text-destructive ml-auto max-w-sm text-xs">
          {row.error} {Object.entries(row.fields).map(([key, messages]) => `${ADJUSTMENT_LABELS[key] ?? ""}：${messages.join(" ")}`).join("；")}
        </p>
      ) : null}
    </div>
  );
}

function Line({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={`money pr-2 ${tone ?? ""}`}>{value}</dd>
    </div>
  );
}

/** What an opened expense shows: its items, the receipt's tax, tip and discount, and the check
 * against what was paid. */
export function LinesTable({ expense, events }: { expense: ExpenseDetail; events: GridEvents }) {
  const name = expense.merchant || expense.title;
  if (expense.total_only) {
    return (
      <div className="grid gap-2">
        <p className="text-muted-foreground text-sm">只有總額：這筆沒有品項明細可以補。</p>
        <ReceiptTotals expense={expense} events={events} />
      </div>
    );
  }
  return (
    <div className="grid gap-3">
      {/* Wider than a phone: it scrolls sideways (accepted in the decision) rather than turning into a dialog. */}
      <div className="relative overflow-x-auto">
        <table className="w-full min-w-[1000px] table-fixed text-sm">
          <colgroup>
            <col /><col className="w-20" /><col className="w-16" /><col className="w-20" /><col className="w-20" />
            <col className="w-28" /><col className="w-28" /><col className="w-32" /><col className="w-24" />
          </colgroup>
          <thead className="text-muted-foreground text-xs">
            <tr className="[&>th]:px-2 [&>th]:pb-1.5 [&>th]:font-medium">
              <th className="text-left">收據原文</th>
              <th className="text-right">原價</th>
              <th className="text-right">折扣</th>
              <th className="text-right">折後</th>
              <th className="text-right" title="加上分到的稅、小費，扣掉分到的整張折扣">稅後</th>
              <th className="text-right">數量</th>
              <th className="text-right">淨重</th>
              <th className="text-right">單價</th>
              <th><span className="sr-only">狀態</span></th>
            </tr>
          </thead>
          <tbody>
            {expense.lines.map((line) => <LineRow key={line.id} line={line} events={events} />)}
            <NewLineRow expense={expense} label={name} events={events} />
          </tbody>
        </table>
      </div>
      <ReceiptTotals expense={expense} events={events} />
      {expense.summary.unknown_amount_count > 0 ? (
        <p className="text-muted-foreground text-xs">{expense.summary.unknown_amount_count} 項金額未確認，沒有算進原價合計。</p>
      ) : null}
      <p className="text-muted-foreground text-xs leading-relaxed">
        點格子直接改，離開格子就存；Esc 還原。有金額時，單價和數量／淨重填一個，另一個會推算（≈）。折扣可填 2 或 20%；
        收據只印折後價就填「折後」，原價會算出來。稅照收據填，小費和整張折扣可填 %。
      </p>
    </div>
  );
}

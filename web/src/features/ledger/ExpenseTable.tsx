/** The chosen day as a table you keep typing into (pm/decisions/calendar-day-is-the-entry-table.md):
 * one row per expense, edited in place and saved as you leave a cell; the last row is new and is
 * created on Enter, on that day; a row opens to its lines (pm/decisions/inline-grid-autosave.md). */
import { useQueryClient } from "@tanstack/react-query";
import { CheckIcon, ChevronRightIcon, EyeOffIcon, MoreHorizontalIcon, ReceiptTextIcon, Trash2Icon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { api } from "@/shared/api/client";
import { cn } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/shared/ui/dropdown-menu";
import { GridCell, RowError, RowState, useGridRow, useReportRisk, type GridRow } from "@/shared/ui/grid";

import { expenseChanged, useCategories, useDeleteExpense, useUpdateExpense } from "./api";
import { CategoryDot } from "./category";
import { LinesTable, type GridEvents } from "./LinesTable";
import type { ExpenseDetail } from "./types";

type Draft = { title: string; amount: string; category_id: string; merchant: string; date: string; notes: string };
const LABELS: Record<string, string> = { title: "名稱", amount: "實付", category_id: "分類", merchant: "店家", date: "日期", notes: "備註" };
const COLUMNS = 8;

const toDraft = (expense: ExpenseDetail): Draft => ({
  title: expense.title, amount: expense.amount, category_id: String(expense.category.id), merchant: expense.merchant,
  date: expense.date, notes: expense.notes,
});

function changes(changed: Partial<Draft>) {
  const body: Record<string, string | number> = { ...changed };
  if (changed.category_id !== undefined) body.category_id = Number(changed.category_id);
  return body;
}

function Cells({ row, label, firstRef, disabled, onCategory }: {
  row: GridRow<Draft>; label: string; firstRef?: React.Ref<HTMLInputElement>; disabled?: boolean;
  onCategory: (id: string) => void;
}) {
  const categories = useCategories();
  const input = (key: keyof Draft, placeholder: string, extra: React.ComponentProps<"input"> = {}) => (
    <input aria-label={`${LABELS[key]}，${label}`} value={row.value[key]} placeholder={placeholder} disabled={disabled}
      aria-invalid={Boolean(row.fields[key]) || undefined} onChange={(event) => row.set(key, event.target.value)} {...extra} />
  );
  const category = categories.data?.find((item) => String(item.id) === row.value.category_id);
  return (
    <>
      <td><GridCell row={row} keys={["title"]} className="[&_input]:font-medium">{input("title", row.creating ? "＋ 新增支出：名稱" : "", { maxLength: 120, ref: firstRef })}</GridCell></td>
      <td><GridCell row={row} keys={["amount"]} className="[&_input]:text-right [&_input]:tabular-nums">{input("amount", "0.00", { inputMode: "decimal" })}</GridCell></td>
      <td>
        <GridCell row={row} keys={["category_id"]} className="gap-1 pl-2 [&_select]:w-full [&_select]:text-foreground">
          {category ? <CategoryDot name={category.name} /> : null}
          <select aria-label={`${LABELS.category_id}，${label}`} value={row.value.category_id} disabled={disabled}
            aria-invalid={Boolean(row.fields.category_id) || undefined} onChange={(event) => onCategory(event.target.value)}>
            <option value="" disabled>分類</option>
            {(categories.data ?? []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </GridCell>
      </td>
      <td><GridCell row={row} keys={["merchant"]}>{input("merchant", "", { maxLength: 120 })}</GridCell></td>
      <td><GridCell row={row} keys={["date"]}>{input("date", "", { type: "date" })}</GridCell></td>
      <td><GridCell row={row} keys={["notes"]}>{input("notes", "", { maxLength: 500 })}</GridCell></td>
    </>
  );
}

function ExpenseRow({ expense, open, onToggle, aside, events }: {
  expense: ExpenseDetail; open: boolean; onToggle: () => void; aside?: React.ReactNode; events: GridEvents;
}) {
  const client = useQueryClient();
  const update = useUpdateExpense();
  const remove = useDeleteExpense();
  const [deleting, setDeleting] = useState(false);
  const row = useGridRow(toDraft(expense), async (_next, changed) => {
    const stored = await api.patch<ExpenseDetail>(`/api/expenses/${expense.id}`, changes(changed));
    expenseChanged(client, stored);
    if (changed.date && changed.date !== expense.date) toast.success(`已移到 ${stored.date}`);
    return toDraft(stored);
  }, { onLost: (message) => events.onLost(`「${expense.title}」的修改沒有存成功：${message}`) });
  useReportRisk(events.report, `${expense.id}`, row.atRisk);
  const unreviewed = expense.reviewed_at === null;
  const kind = expense.line_count ? `${expense.line_count} 項` : expense.total_only ? "只有總額" : "尚未補明細";
  return (
    <>
      <tr className={cn("border-t", unreviewed && "bg-warning/30")}>
        <td className="px-1">
          <div className="flex items-center">
            <Button variant="ghost" size="icon-sm" aria-expanded={open} aria-label={`${open ? "收起" : "展開"} ${expense.title} 的品項（${kind}）`}
              onClick={onToggle}>
              <ChevronRightIcon className={cn("transition-transform", open && "rotate-90")} />
            </Button>
            {unreviewed ? <span title="自動入帳，待確認" className="bg-warning-foreground size-1.5 rounded-full"><span className="sr-only">待確認</span></span> : null}
          </div>
        </td>
        <Cells row={row} label={expense.title} onCategory={(id) => { row.set("category_id", id); row.leave(); }} />
        <td className="px-1 whitespace-nowrap">
          <div className="flex items-center justify-end gap-1">
            <RowState row={row} name={expense.title} />
            {aside}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" aria-label={`更多動作 ${expense.title}`}><MoreHorizontalIcon /></Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => update.mutate({ id: expense.id, changes: { reviewed: unreviewed } })}>
                  {unreviewed ? <><CheckIcon /> 看過了</> : <><EyeOffIcon /> 改回待確認</>}
                </DropdownMenuItem>
                {!expense.line_count ? (
                  <DropdownMenuItem onSelect={() => update.mutate({ id: expense.id, changes: { total_only: !expense.total_only } })}>
                    <ReceiptTextIcon /> {expense.total_only ? "改成可以記品項" : "標記只有總額"}
                  </DropdownMenuItem>
                ) : null}
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" onSelect={() => setDeleting(true)}><Trash2Icon /> 刪除</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          <ConfirmDialog open={deleting} onOpenChange={setDeleting} destructive pending={remove.isPending}
            title={`刪除「${expense.title}」？`} confirmLabel="刪除"
            description={expense.line_count ? `連同 ${expense.line_count} 個品項一起刪除，不能復原。` : "刪除後不能復原。"}
            onConfirm={() => remove.mutate(expense.id, { onSuccess: () => { setDeleting(false); toast.success("已刪除"); } })} />
        </td>
      </tr>
      <RowError row={row} labels={LABELS} colSpan={COLUMNS} />
      {open ? (
        <tr>
          <td colSpan={COLUMNS} className="bg-muted/30 p-0">
            <div className="sticky left-0 px-3 pt-2 pb-4" style={{ width: "var(--table-box, 100%)" }}>
              <LinesTable expense={expense} events={events} />
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}

function NewExpenseRow({ day, events }: { day: string; events: GridEvents }) {
  const client = useQueryClient();
  const first = useRef<HTMLInputElement>(null);
  const next = useRef(false);
  const blank: Draft = { title: "", amount: "", category_id: "", merchant: "", date: day, notes: "" };
  const row = useGridRow(blank, async (draft) => {
    const body: Record<string, unknown> = { title: draft.title, amount: draft.amount, date: draft.date || day,
      merchant: draft.merchant, notes: draft.notes };
    if (draft.category_id) body.category_id = Number(draft.category_id);
    const stored = await api.post<ExpenseDetail>("/api/expenses", body);
    expenseChanged(client, stored);
    if (stored.date !== day) toast.success(`已記在 ${stored.date}`);
    next.current = true;
  }, { create: true });
  useReportRisk(events.report, "new", row.atRisk);
  const saving = row.status === "saving";
  useEffect(() => { // keep going: after adding, the cursor waits in the next new row
    if (!saving && next.current) {
      next.current = false;
      first.current?.focus();
    }
  }, [saving]);
  return (
    <>
      <tr className="border-t">
        <td />
        <Cells row={row} label="新增支出" firstRef={first} disabled={saving} onCategory={(id) => row.set("category_id", id)} />
        <td className="px-1 text-right whitespace-nowrap"><RowState row={row} name="支出" /></td>
      </tr>
      <RowError row={row} labels={LABELS} colSpan={COLUMNS} />
    </>
  );
}

/** The day's expenses and the row that adds the next one. `aside` puts what another feature knows
 * about an expense (the receipt it came from) in its row. */
export function ExpenseTable({ day, expenses, open, onToggle, aside, events }: {
  day: string; expenses: ExpenseDetail[]; open: number[]; onToggle: (id: number) => void;
  aside?: (expense: ExpenseDetail) => React.ReactNode; events: GridEvents;
}) {
  // The opened lines stay in view while the expense table scrolls sideways: they are pinned to the
  // left and as wide as the box the table scrolls in, which this measures.
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = box.current;
    if (!element) return;
    const measure = () => element.style.setProperty("--table-box", `${element.clientWidth}px`);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return (
    <div ref={box} className="relative overflow-x-auto rounded-xl border bg-card shadow-xs">
      {/* Wider than a phone or a narrow window: it scrolls sideways (accepted in the decision). */}
      <table className="w-full min-w-[940px] table-fixed text-sm">
        <colgroup>
          <col className="w-12" /><col /><col className="w-24" /><col className="w-28" /><col className="w-32" />
          <col className="w-36" /><col className="w-36" /><col className="w-28" />
        </colgroup>
        <thead className="text-muted-foreground text-xs">
          <tr className="[&>th]:px-2 [&>th]:pt-2.5 [&>th]:pb-1.5 [&>th]:text-left [&>th]:font-medium">
            <th><span className="sr-only">品項</span></th>
            <th>名稱</th>
            <th className="text-right">實付</th>
            <th>分類</th>
            <th>店家</th>
            <th>日期</th>
            <th>備註</th>
            <th><span className="sr-only">狀態與動作</span></th>
          </tr>
        </thead>
        <tbody>
          {expenses.map((expense) => (
            <ExpenseRow key={expense.id} expense={expense} open={open.includes(expense.id)} onToggle={() => onToggle(expense.id)}
              aside={aside?.(expense)} events={events} />
          ))}
          <NewExpenseRow key={day} day={day} events={events} />
        </tbody>
      </table>
      <p className="text-muted-foreground border-t px-3 py-2 text-xs">
        點格子直接改，離開格子就存，Esc 還原。最後一列打好按 Enter 新增，日期是這一天；改日期會把那筆移到那天。▸ 打開品項。
      </p>
    </div>
  );
}

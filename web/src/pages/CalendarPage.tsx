import { XIcon } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router";

import { useToday } from "@/features/auth";
import { ExpenseTable, useDay, useMonths, type GridEvents } from "@/features/ledger";
import { ReceiptThumb, useReceiptsForExpenses } from "@/features/receipts";
import { dayLabel, money } from "@/shared/lib/format";
import { Button } from "@/shared/ui/button";
import { DayPicker, useDayPicker } from "@/shared/ui/day-picker";
import { Notice, Skeleton } from "@/shared/ui/feedback";
import { useRiskRegistry } from "@/shared/ui/grid";

const DAY = /^\d{4}-\d{2}-\d{2}$/;
// Sums of server money strings, in cents so 0.10 + 0.20 stays 0.30.
const sumMoney = (amounts: (string | undefined)[]) =>
  (amounts.reduce((total, amount) => total + Math.round(Number(amount ?? 0) * 100), 0) / 100).toFixed(2);

/** The chosen day first (pm/decisions/day-first-layout-adopted.md): the week strip, or the month,
 * above only picks it. The day is the table you keep typing into
 * (pm/decisions/calendar-day-is-the-entry-table.md); each expense's receipt shows in its row. */
export function CalendarPage() {
  const today = useToday();
  const [params, setParams] = useSearchParams();
  const day = DAY.test(params.get("day") ?? "") ? params.get("day")! : today;
  const focus = Number(params.get("expense")) || null;
  const picker = useDayPicker(day);
  const months = useMonths(picker.months);
  const data = useDay(day);
  const expenses = data.data?.date === day ? data.data.expenses : [];
  const receipts = useReceiptsForExpenses(expenses.map((expense) => expense.id));
  const [open, setOpen] = useState<number[]>(focus ? [focus] : []);
  const [lost, setLost] = useState("");
  const risk = useRiskRegistry();
  const events: GridEvents = { report: risk.report, onLost: setLost };

  const choose = (next: string) => {
    if (next === day) return;
    if (!risk.confirmLeave()) return; // a half-typed row or an edit that failed would be lost
    setOpen([]);
    setLost("");
    setParams((old) => {
      const merged = new URLSearchParams(old);
      merged.set("day", next);
      merged.delete("expense");
      return merged;
    });
  };
  const toggle = (id: number) => {
    if (open.includes(id) && !risk.confirmLeave(`${id}:`)) return;
    setOpen((ids) => (ids.includes(id) ? ids.filter((other) => other !== id) : [...ids, id]));
  };
  const week = picker.mode === "week";
  const total = !months.known ? "…" : week
    ? `本週 ${money(sumMoney(picker.cells.map((date) => months.days.get(date)?.total)))}`
    : `本月 ${money(months.totals[picker.month])}`;

  return (
    <div className="grid min-w-0 gap-4 [&>*]:min-w-0">
      <DayPicker picker={picker} selected={day} today={today} onSelect={choose} busy={months.loading} label="選擇日期，看當天支出"
        summary={total}
        describe={(date) => {
          const row = months.days.get(date);
          return row ? `支出 ${money(row.total)}，${row.merchants.join("、")}` : months.known ? "無支出" : "讀取中";
        }}
        cell={(date, compact) => {
          const row = months.days.get(date);
          if (!row) return null;
          return (
            <>
              <span className="money text-[11px] leading-4 font-medium">{compact ? Math.round(Number(row.total)).toLocaleString("en-US") : money(row.total)}</span>
              {!compact ? (
                <span className="flex w-full min-w-0 flex-col text-[10px] leading-3.5 opacity-80">
                  {row.merchants.slice(0, 2).map((name) => <span key={name} className="truncate" title={name}>{name}</span>)}
                  {row.merchants.length > 2 ? <span>+{row.merchants.length - 2} 家</span> : null}
                </span>
              ) : null}
            </>
          );
        }} />

      {months.error ? <Notice tone="destructive">{months.error.message}</Notice> : null}

      <section aria-label={`${dayLabel(day)} 的支出`} className="grid min-w-0 gap-2 [&>*]:min-w-0">
        <header className="flex items-baseline justify-between gap-3 px-1">
          <h1 className="text-lg font-semibold">{dayLabel(day)}</h1>
          <p className="text-muted-foreground money text-sm">
            {data.isPending ? "…" : expenses.length ? `${expenses.length} 筆，共 ${money(data.data?.total)}` : "還沒有支出"}
          </p>
        </header>
        {lost ? (
          <Notice tone="destructive">
            <div className="flex items-start justify-between gap-2">
              {lost}
              <Button variant="ghost" size="icon-sm" aria-label="關閉提示" onClick={() => setLost("")}><XIcon /></Button>
            </div>
          </Notice>
        ) : null}
        {data.isError ? <Notice tone="destructive">{data.error.message}</Notice> : null}
        {data.isPending ? (
          <Skeleton className="h-40" />
        ) : (
          <ExpenseTable day={day} expenses={expenses} open={open} onToggle={toggle} events={events}
            aside={(expense) => {
              const receipt = receipts.data?.[String(expense.id)];
              return receipt ? <ReceiptThumb receipt={receipt} className="size-7" /> : null;
            }} />
        )}
      </section>
    </div>
  );
}

/** Picking a day (pm/decisions/day-first-layout-adopted.md), moved from the old DayPicker.tsx: the
 * chosen day is the page; a week strip on top picks it and opens into a small month.
 *
 * - The week (Sunday to Saturday) by default; 月 opens the month, whose cells hold less.
 * - ‹ › move the week or month on screen, not the chosen day; 今天 chooses today.
 * - Choosing a day keeps the week or month open; a grey day of the next month brings that month.
 * - The week's or month's total sits small beside the dates, instead of a page heading.
 * What each day shows comes from the page (`cell`), so this knows nothing about expenses. */
import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react";
import { useEffect, useState } from "react";
import type * as React from "react";

import { dayText, parseDay, shiftMonth } from "@/shared/lib/format";
import { cn } from "@/shared/lib/utils";

import { Button } from "./button";

const WEEKDAYS = ["日", "一", "二", "三", "四", "五", "六"];
export type PickerMode = "week" | "month";

export function addDays(day: string, by: number): string {
  const date = parseDay(day);
  date.setDate(date.getDate() + by);
  return dayText(date);
}

export function weekCells(day: string): string[] {
  const sunday = addDays(day, -parseDay(day).getDay());
  return Array.from({ length: 7 }, (_, index) => addDays(sunday, index));
}

export function monthCells(month: string): string[] {
  const first = parseDay(`${month}-01`);
  const days = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
  const count = Math.ceil((first.getDay() + days) / 7) * 7;
  const start = addDays(`${month}-01`, -first.getDay());
  return Array.from({ length: count }, (_, index) => addDays(start, index));
}

const monthDay = (day: string) => `${Number(day.slice(5, 7))}月${Number(day.slice(8))}日`;

/** Which week or month is on screen, and whether the month is open; the chosen day is the page's. */
export function useDayPicker(selected: string) {
  const [view, setView] = useState(selected); // a day inside the week or month on screen
  const [mode, setMode] = useState<PickerMode>("week");
  useEffect(() => setView(selected), [selected]); // a day chosen anywhere brings its week or month
  const month = view.slice(0, 7);
  const cells = mode === "week" ? weekCells(view) : monthCells(month);
  // A week can reach into the month before or after; the month view needs only its own.
  const months = [...new Set(mode === "week" ? cells.map((day) => day.slice(0, 7)) : [month])];
  return {
    view, mode, month, cells, months,
    step: (by: number) => setView(mode === "week" ? addDays(view, 7 * by) : `${shiftMonth(month, by)}-01`),
    showMonth: (value: string) => { if (/^\d{4}-\d{2}$/.test(value)) setView(`${value}-01`); },
    setMode: (next: PickerMode) => {
      if (next === "week") setView(selected);
      setMode(next);
    },
  };
}

export type Picker = ReturnType<typeof useDayPicker>;

export function DayPicker({ picker, selected, today, onSelect, summary, describe, cell, busy, label }: {
  picker: Picker;
  selected: string;
  today: string;
  onSelect: (day: string) => void;
  summary: React.ReactNode; // the week's or month's total
  describe: (day: string) => string; // what a screen reader says for the day
  cell: (day: string, compact: boolean) => React.ReactNode; // what the day shows under its number
  busy?: boolean;
  label: string;
}) {
  const { mode, cells, month } = picker;
  const week = mode === "week";
  return (
    <section aria-label={label} className="rounded-xl border bg-card p-2 shadow-xs sm:p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <div className="flex min-w-0 flex-[1_1_auto] items-baseline gap-2 px-1">
          {week ? (
            <strong className="text-sm font-semibold whitespace-nowrap">{monthDay(cells[0])} – {monthDay(cells[6])}</strong>
          ) : (
            <input type="month" aria-label="選擇月份" value={month} onChange={(event) => picker.showMonth(event.target.value)}
              className="rounded-md bg-transparent text-sm font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ring/40" />
          )}
          <span className="text-muted-foreground money truncate text-xs">{summary}</span>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="outline" size="sm" onClick={() => onSelect(today)}>今天</Button>
          <Button variant="ghost" size="icon-sm" aria-label={week ? "上一週" : "上一個月"} onClick={() => picker.step(-1)}><ChevronLeftIcon /></Button>
          <Button variant="ghost" size="icon-sm" aria-label={week ? "下一週" : "下一個月"} onClick={() => picker.step(1)}><ChevronRightIcon /></Button>
          <div role="group" aria-label="日曆範圍" className="bg-muted ml-1 inline-flex rounded-md p-0.5 text-xs">
            {(["week", "month"] as const).map((value) => (
              <button key={value} type="button" aria-pressed={mode === value} onClick={() => picker.setMode(value)}
                className={cn("rounded px-2.5 py-1 transition-colors", mode === value ? "bg-card text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground")}>
                {value === "week" ? "週" : "月"}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div aria-busy={busy || undefined}>
        <div aria-hidden className="text-muted-foreground grid grid-cols-7 pb-1 text-center text-[11px]">
          {WEEKDAYS.map((name) => <span key={name}>{name}</span>)}
        </div>
        <div className="grid grid-cols-7 gap-1">
          {cells.map((day) => {
            const outside = !week && !day.startsWith(month);
            const chosen = day === selected;
            return (
              <button key={day} type="button" aria-pressed={chosen} onClick={() => onSelect(day)}
                aria-label={`${day}，${outside ? "非本月" : describe(day)}`}
                className={cn(
                  "flex min-w-0 flex-col items-center rounded-lg px-0.5 py-1.5 text-center transition-colors hover:bg-accent",
                  week ? "min-h-20 gap-0.5" : "min-h-12 gap-0",
                  outside && "opacity-40",
                  day === today && !chosen && "ring-1 ring-primary/40",
                  chosen && "bg-primary text-primary-foreground hover:bg-primary/90",
                )}>
                <span className={cn("text-sm leading-5", day === today && "font-semibold")}>{parseDay(day).getDate()}</span>
                {outside ? null : cell(day, !week)}
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}

import { AlertTriangleIcon, CheckIcon, ListChecksIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { CategorySelect, useUpdateExpense, type ExpenseDetail } from "@/features/ledger";
import { dateDoubt, ReceiptThumb, type ReceiptCard } from "@/features/receipts";
import { money } from "@/shared/lib/format";
import { Button } from "@/shared/ui/button";
import { Notice } from "@/shared/ui/feedback";
import { Input } from "@/shared/ui/input";

// The model's own notes that question the date: checks cannot catch a wrong date
// (pm/issues/auto-post-wrong-date.md), so they are shown up front here.
const ABOUT_DATE = /date|日期|year|month/i;

/** A date that saves as soon as a whole date is picked (a date picker has no "leaving the field"). */
function DateField({ value, onPick }: { value: string; onPick: (date: string) => void }) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  return (
    <Input type="date" value={draft} aria-label="日期" className="h-8 w-[9.5rem]"
      onChange={(event) => {
        setDraft(event.target.value);
        if (/^\d{4}-\d{2}-\d{2}$/.test(event.target.value) && event.target.value !== value) onPick(event.target.value);
      }} />
  );
}

/** An expense posted automatically, beside its receipt: fix the date or category in place, then
 * say you have seen it. */
export function ReviewRow({ expense, receipt }: { expense: ExpenseDetail; receipt?: ReceiptCard }) {
  const update = useUpdateExpense();
  const navigate = useNavigate();
  const warnings = receipt?.reading?.warnings ?? [];
  // The expense's date as it is now, so the doubt goes away once the date is corrected.
  const doubt = receipt ? dateDoubt(expense.date, receipt.created_at) : null;
  const dateWarnings = [...(doubt ? [doubt] : []), ...warnings.filter((warning) => ABOUT_DATE.test(warning))];
  const summary = expense.summary;
  const balanced = summary.unrecorded === "0.00" && summary.unknown_amount_count === 0 && expense.lines.length > 0;
  const change = (changes: Parameters<typeof update.mutate>[0]["changes"], message: string) =>
    update.mutate({ id: expense.id, changes }, {
      onSuccess: () => toast.success(message),
      onError: (error) => toast.error(error.message),
    });

  return (
    <article className="grid gap-3 rounded-xl border bg-card p-3 shadow-xs sm:p-4">
      <div className="flex gap-3">
        {receipt ? <ReceiptThumb receipt={receipt} className="size-16 sm:size-20" /> : null}
        <div className="grid min-w-0 flex-1 gap-2">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate font-medium">{expense.title}</p>
              <p className="text-muted-foreground text-xs">
                {expense.line_count} 個品項{balanced ? " · 品項剛好等於實付" : ""}
              </p>
            </div>
            <p className="money shrink-0 text-lg font-semibold">{money(expense.amount)}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-1.5 text-sm">
              <span className="text-muted-foreground">日期</span>
              <DateField value={expense.date} onPick={(date) => change({ date }, "已改日期")} />
            </label>
            <label className="flex items-center gap-1.5 text-sm">
              <span className="text-muted-foreground">分類</span>
              <CategorySelect value={expense.category.id} className="h-8 w-28"
                onChange={(category_id) => change({ category_id }, "已改分類")} />
            </label>
          </div>
        </div>
      </div>
      {dateWarnings.length ? (
        <Notice tone="warning" icon={<AlertTriangleIcon />}>
          <p className="font-medium">讀的時候日期有疑問，請對一下照片</p>
          <ul className="list-disc pl-4 text-xs">{dateWarnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
        </Notice>
      ) : warnings.length ? (
        <details className="text-xs">
          <summary className="text-muted-foreground cursor-pointer select-none">模型讀的時候提醒了 {warnings.length} 件事</summary>
          <ul className="text-muted-foreground mt-1 list-disc pl-5">{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
        </details>
      ) : null}
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="outline" size="sm" onClick={() => navigate(`/calendar?day=${expense.date}&expense=${expense.id}`)}>
          <ListChecksIcon /> 核對品項
        </Button>
        <Button size="sm" onClick={() => change({ reviewed: true }, "好，這筆確認了")} disabled={update.isPending}>
          <CheckIcon /> 看過了，沒問題
        </Button>
      </div>
    </article>
  );
}

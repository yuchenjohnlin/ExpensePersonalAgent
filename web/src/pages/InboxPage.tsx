import { AlertCircleIcon, CheckCircle2Icon, InboxIcon, Loader2Icon, ReceiptIcon } from "lucide-react";
import type * as React from "react";
import { Link } from "react-router";

import { useSession, useToday } from "@/features/auth";
import { useUnreviewed } from "@/features/ledger";
import { ReceiptListItem, useReceipts, useReceiptsForExpenses } from "@/features/receipts";
import { dayLabel } from "@/shared/lib/format";
import { Button } from "@/shared/ui/button";
import { EmptyState, Notice, Skeleton } from "@/shared/ui/feedback";

import { ReviewRow } from "./inbox/ReviewRow";

/** Home: only what needs you. Receipts that could not be posted by themselves, and expenses that
 * were, waiting for a look (pm/decisions/expense-review-status-not-drafts.md). */
export function InboxPage() {
  const today = useToday();
  const user = useSession().data?.user;
  const needs = useReceipts("needs_review");
  const unreviewed = useUnreviewed();
  const receipts = useReceiptsForExpenses((unreviewed.data ?? []).map((expense) => expense.id));
  const reading = needs.data?.counts.reading ?? 0;
  const waiting = needs.data?.receipts ?? [];
  const toConfirm = unreviewed.data ?? [];
  const loading = needs.isPending || unreviewed.isPending;

  return (
    <div className="grid gap-6">
      <header>
        <p className="text-muted-foreground text-sm">{dayLabel(today)}{user ? ` · ${user.username}` : ""}</p>
        <h1 className="text-2xl font-semibold">收件匣</h1>
      </header>

      <div className="grid grid-cols-3 gap-2 sm:gap-3">
        <Stat icon={<AlertCircleIcon className="text-warning-foreground" />} label="要看一下" value={loading ? null : waiting.length} />
        <Stat icon={<CheckCircle2Icon className="text-primary" />} label="待確認" value={loading ? null : toConfirm.length} />
        <Stat icon={<Loader2Icon className={reading ? "animate-spin text-info-foreground" : "text-muted-foreground"} />}
          label="讀取中" value={needs.isPending ? null : reading} />
      </div>

      {reading ? (
        <Notice tone="info" icon={<Loader2Icon className="animate-spin" />}>
          {reading} 張收據正在讀取，讀完會出現在下面，或直接入帳。
        </Notice>
      ) : null}

      {loading ? (
        <div className="grid gap-3"><Skeleton className="h-28" /><Skeleton className="h-28" /></div>
      ) : !waiting.length && !toConfirm.length ? (
        <EmptyState icon={<InboxIcon />} title="都處理好了">
          <p>新的收據拍下來上傳，讀完會出現在這裡。</p>
          <Button asChild className="mt-3"><Link to="/receipts"><ReceiptIcon /> 上傳收據</Link></Button>
        </EmptyState>
      ) : null}

      {waiting.length ? (
        <section className="grid gap-3">
          <SectionTitle title="要看一下的收據" note="沒辦法自動入帳，原因寫在每張上。" />
          <div className="grid gap-3 lg:grid-cols-2">
            {waiting.map((receipt) => <ReceiptListItem key={receipt.id} receipt={receipt} />)}
          </div>
          {(needs.data?.total ?? 0) > waiting.length ? (
            <Button variant="link" asChild className="justify-self-start"><Link to="/receipts?tab=needs_review">看全部</Link></Button>
          ) : null}
        </section>
      ) : null}

      {toConfirm.length ? (
        <section className="grid gap-3">
          <SectionTitle title="自動入帳，請確認" note="已經算進帳裡了。分類先記成「未分類」；日期或金額不對就直接改。" />
          <div className="grid gap-3">
            {toConfirm.map((expense) => (
              <ReviewRow key={expense.id} expense={expense} receipt={receipts.data?.[String(expense.id)]} />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: number | null }) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border bg-card p-3 shadow-xs sm:flex-row sm:items-center sm:gap-3 sm:p-4">
      <div className="[&_svg]:size-5">{icon}</div>
      <div>
        <p className="money text-xl font-semibold leading-none sm:text-2xl">{value ?? "–"}</p>
        <p className="text-muted-foreground mt-1 text-xs">{label}</p>
      </div>
    </div>
  );
}

function SectionTitle({ title, note }: { title: string; note: string }) {
  return (
    <div>
      <h2 className="font-semibold">{title}</h2>
      <p className="text-muted-foreground text-sm">{note}</p>
    </div>
  );
}

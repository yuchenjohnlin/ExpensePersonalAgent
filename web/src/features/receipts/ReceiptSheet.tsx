import { AlertTriangleIcon, CalendarDaysIcon, ExternalLinkIcon, InfoIcon, Loader2Icon, RotateCcwIcon, Undo2Icon } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { ApiError } from "@/shared/api/client";
import { ago, dayLabel, money } from "@/shared/lib/format";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Notice, Skeleton } from "@/shared/ui/feedback";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/shared/ui/sheet";

import { useReadAgain, useReceipt, useUnpost } from "./api";
import { useOpenedReceipt, useOpenReceipt } from "./open";
import { PostForm } from "./PostForm";
import { dateDoubt, ReceiptStatusBadge, receiptTitle, summarizeReasons } from "./status";
import type { ReceiptCard } from "./types";

/** The receipt named in the URL (?receipt=), over whatever page is open. */
export function ReceiptSheet() {
  const id = useOpenedReceipt();
  const open = useOpenReceipt();
  return (
    <Sheet open={id !== null} onOpenChange={(isOpen) => !isOpen && open(null)}>
      <SheetContent className="sm:max-w-xl lg:max-w-4xl">
        {id !== null ? <ReceiptDetail id={id} /> : null}
      </SheetContent>
    </Sheet>
  );
}

function ReceiptDetail({ id }: { id: number }) {
  const receipt = useReceipt(id);
  if (receipt.isPending) {
    return (
      <div className="grid gap-4 p-6">
        <SheetTitle className="sr-only">收據</SheetTitle>
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }
  if (receipt.isError) {
    return (
      <div className="p-6">
        <SheetTitle className="text-lg font-semibold">收據</SheetTitle>
        <p className="text-muted-foreground mt-2">{receipt.error instanceof ApiError ? receipt.error.message : "讀不到這張收據。"}</p>
      </div>
    );
  }
  const card = receipt.data;
  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <header className="sticky top-0 z-10 border-b bg-background/95 px-5 py-4 pr-14 backdrop-blur">
        <SheetTitle className="truncate text-lg font-semibold">{receiptTitle(card)}</SheetTitle>
        <SheetDescription asChild>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <ReceiptStatusBadge receipt={card} />
            <span>上傳於 {ago(card.created_at)} · {card.photos.length} 張照片</span>
          </div>
        </SheetDescription>
      </header>
      <div className="grid flex-1 gap-5 p-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="grid content-start gap-4 lg:order-2">
          <Status card={card} />
        </div>
        <Photos card={card} />
      </div>
    </div>
  );
}

function Photos({ card }: { card: ReceiptCard }) {
  return (
    <section aria-label="照片" className="grid content-start gap-3 lg:order-1">
      {card.photos.map((photo) => (
        <figure key={photo.id} className="overflow-hidden rounded-xl border bg-muted">
          <img src={photo.preview_url} alt={`照片 ${photo.position}`} className="w-full" />
          <figcaption className="flex items-center justify-between px-3 py-1.5 text-xs text-muted-foreground">
            <span>{photo.position}. {photo.original_name}</span>
            <a href={photo.original_url} className="inline-flex items-center gap-1 hover:text-foreground">原檔 <ExternalLinkIcon className="size-3" /></a>
          </figcaption>
        </figure>
      ))}
    </section>
  );
}

function Status({ card }: { card: ReceiptCard }) {
  const readAgain = useReadAgain();
  if (card.state === "reading") {
    return (
      <Notice tone="info" icon={<Loader2Icon className="animate-spin" />}>
        <p className="font-medium">正在讀取這張收據</p>
        <p>通常要 1 到 3 分鐘。可以先去別的地方，讀完會自動入帳，或放進「要看一下」。</p>
      </Notice>
    );
  }
  return (
    <>
      {card.state === "needs_review" ? (
        <Notice tone="warning" icon={<AlertTriangleIcon />}>
          <p className="font-medium">沒有自動入帳，因為：</p>
          <ul className="mt-1 list-disc pl-4">{summarizeReasons(card.reasons).map((reason) => <li key={reason}>{reason}</li>)}</ul>
        </Notice>
      ) : null}
      {card.posting?.expense ? <Posted card={card} /> : null}
      <ReadingFacts card={card} />
      {card.state === "needs_review" ? (
        <>
          <PostForm key={card.reading?.id ?? 0} receipt={card} />
          <Button variant="outline" disabled={readAgain.isPending}
            onClick={() => readAgain.mutate(card.id, { onError: (error) => toast.error(error.message) })}>
            <RotateCcwIcon /> 重新讀取
          </Button>
        </>
      ) : null}
    </>
  );
}

function Posted({ card }: { card: ReceiptCard }) {
  const navigate = useNavigate();
  const unpost = useUnpost();
  const [confirming, setConfirming] = useState(false);
  const expense = card.posting!.expense!;
  const skipped = card.posting!.skipped;
  return (
    <section className="grid gap-3 rounded-xl border bg-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-muted-foreground text-xs">{card.posting!.mode === "auto" ? "自動入帳為" : "入帳為"}</p>
          <p className="font-medium">{expense.title}</p>
          <p className="text-muted-foreground text-sm">{dayLabel(expense.date)} · {expense.category} · {expense.line_count} 個品項</p>
        </div>
        <div className="text-right">
          <p className="money text-lg font-semibold">{money(expense.amount)}</p>
          {expense.reviewed_at === null ? <Badge variant="warning">待確認</Badge> : null}
        </div>
      </div>
      {skipped.length ? (
        <Notice tone="info" icon={<InfoIcon />}>
          沒有變成品項：{skipped.map((item) => `${item.description}（${item.amount ?? "?"}，${item.reason}）`).join("、")}
        </Notice>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={() => navigate(`/calendar?day=${expense.date}&expense=${expense.id}`)}>
          <CalendarDaysIcon /> 到月曆核對品項
        </Button>
        <Button size="sm" variant="outline" onClick={() => setConfirming(true)}><Undo2Icon /> 取消入帳</Button>
      </div>
      <ConfirmDialog open={confirming} onOpenChange={setConfirming} destructive pending={unpost.isPending}
        title="取消入帳？" confirmLabel="取消入帳"
        description={`會刪除支出「${expense.title}」與它的 ${expense.line_count} 個品項；收據和照片留著，可以重新入帳。`}
        onConfirm={() => unpost.mutate(card.id, { onSuccess: () => { setConfirming(false); toast.success("已取消入帳"); } })} />
    </section>
  );
}

function ReadingFacts({ card }: { card: ReceiptCard }) {
  const reading = card.reading;
  if (!reading) return null;
  if (reading.status === "failed") {
    return <Notice tone="destructive" icon={<AlertTriangleIcon />}>讀取失敗：{reading.error_message}</Notice>;
  }
  if (reading.status !== "succeeded") return null;
  const facts: [string, string][] = [
    ["店家", reading.merchant ?? "—"],
    ["日期", reading.date ? dayLabel(reading.date) : "—"],
    ["總額", money(reading.amount)],
    ["稅", reading.tax === null ? "—" : money(reading.tax)],
    ["品項", `${reading.item_count} 項`],
  ];
  return (
    <section className="grid gap-3 rounded-xl border bg-card p-4">
      <p className="text-muted-foreground text-xs">讀到的內容 · {reading.model.split("/").pop()}{reading.elapsed_ms ? ` · ${Math.round(reading.elapsed_ms / 1000)} 秒` : ""}</p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        {facts.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="money">{value}</dd>
          </div>
        ))}
      </dl>
      {dateDoubt(reading.date, card.created_at) ? (
        <Notice tone="warning" icon={<AlertTriangleIcon />}>{dateDoubt(reading.date, card.created_at)}</Notice>
      ) : null}
      {/* A receipt set aside already lists its failed checks as the reasons above. */}
      {reading.checks.length && card.state !== "needs_review" ? (
        <Notice tone="warning" icon={<AlertTriangleIcon />}>
          <p className="font-medium">算術檢查沒過</p>
          <ul className="list-disc pl-4">{summarizeReasons(reading.checks).map((check) => <li key={check}>{check}</li>)}</ul>
        </Notice>
      ) : null}
      {reading.warnings.length ? (
        <details className="text-sm">
          <summary className="text-muted-foreground cursor-pointer select-none">模型讀的時候提醒了 {reading.warnings.length} 件事</summary>
          <ul className="mt-2 list-disc pl-5 text-muted-foreground">{reading.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
        </details>
      ) : null}
    </section>
  );
}

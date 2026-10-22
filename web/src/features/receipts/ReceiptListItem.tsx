import { ago, money, shortDay } from "@/shared/lib/format";
import { cn } from "@/shared/lib/utils";

import { useOpenReceipt } from "./open";
import { ReceiptStatusBadge, receiptTitle, summarizeReasons } from "./status";
import type { ReceiptCard } from "./types";

/** A receipt in a list: its first photo, what was read, and where it stands. Opens the sheet. */
export function ReceiptListItem({ receipt, className }: { receipt: ReceiptCard; className?: string }) {
  const open = useOpenReceipt();
  const expense = receipt.posting?.expense;
  const day = expense?.date ?? receipt.reading?.date;
  const amount = expense?.amount ?? receipt.reading?.amount;
  return (
    <button type="button" onClick={() => open(receipt.id)}
      className={cn("flex w-full items-start gap-3 rounded-xl border bg-card p-3 text-left shadow-xs transition-colors hover:bg-accent/50", className)}>
      <div className="relative shrink-0">
        <img src={receipt.photos[0]?.thumbnail_url} alt="" loading="lazy"
          className="size-16 rounded-lg border bg-muted object-cover" />
        {receipt.photos.length > 1 ? (
          <span className="absolute right-1 bottom-1 rounded bg-black/60 px-1 text-[10px] text-white">{receipt.photos.length} 張</span>
        ) : null}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <p className="truncate font-medium">{receiptTitle(receipt)}</p>
          {amount ? <span className="money shrink-0 font-medium">{money(amount)}</span> : null}
        </div>
        <p className="text-muted-foreground text-xs">
          {day ? shortDay(day) : "日期未知"} · 上傳於 {ago(receipt.created_at)}
        </p>
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <ReceiptStatusBadge receipt={receipt} />
          {receipt.reasons.length ? (
            <span className="text-warning-foreground line-clamp-1 text-xs">{summarizeReasons(receipt.reasons)[0]}</span>
          ) : null}
        </div>
      </div>
    </button>
  );
}

/** Just the photo, as a button that opens the receipt (next to an expense). */
export function ReceiptThumb({ receipt, className }: { receipt: ReceiptCard; className?: string }) {
  const open = useOpenReceipt();
  return (
    <button type="button" onClick={() => open(receipt.id)} aria-label="看收據照片"
      className={cn("shrink-0 overflow-hidden rounded-md border bg-muted transition-opacity hover:opacity-80", className)}>
      <img src={receipt.photos[0]?.thumbnail_url} alt="" loading="lazy" className="size-full object-cover" />
    </button>
  );
}

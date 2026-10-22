import { AlertCircleIcon, CheckCircle2Icon, Loader2Icon } from "lucide-react";

import { parseDay } from "@/shared/lib/format";
import { Badge } from "@/shared/ui/badge";

import type { ReceiptCard } from "./types";

export function ReceiptStatusBadge({ receipt }: { receipt: ReceiptCard }) {
  if (receipt.state === "reading") {
    return <Badge variant="info"><Loader2Icon className="animate-spin" /> 讀取中</Badge>;
  }
  if (receipt.state === "needs_review") {
    return <Badge variant="warning"><AlertCircleIcon /> 要看一下</Badge>;
  }
  const unreviewed = receipt.posting?.expense?.reviewed_at === null;
  return (
    <Badge variant={unreviewed ? "secondary" : "success"}>
      <CheckCircle2Icon /> {unreviewed ? "已入帳・待確認" : "已入帳"}
    </Badge>
  );
}

const ITEM_CHECK = /^第 (\d+) 項的數量或淨重乘單價與該行金額不一致/;

/** The server's reasons, with its one-line-per-item check folded into one line: a receipt whose
 * unit prices were read wrong would otherwise list a dozen near-identical lines. */
export function summarizeReasons(reasons: string[]): string[] {
  const items = reasons.map((reason) => reason.match(ITEM_CHECK)?.[1]).filter((n): n is string => Boolean(n));
  if (items.length < 2) return reasons;
  const listed = items.length > 6 ? `${items.slice(0, 6).join("、")} 等` : items.join("、");
  return [...reasons.filter((reason) => !ITEM_CHECK.test(reason)),
    `${items.length} 個品項的數量（或重量）乘單價對不上金額（第 ${listed} 項），請核對計價方式。`];
}

/** Why a read date looks wrong, or null. Checks cannot catch a wrong date (pm/issues/auto-post-wrong-date.md):
 * the model has read "09/19/26" as 2023, and picked the wrong one of two printed dates. A receipt
 * is usually photographed soon after the purchase, so a date far before the upload is suspect.
 * Only a hint for the person looking; posting does not use it. */
export function dateDoubt(readDate: string | null | undefined, uploadedAt: string): string | null {
  if (!readDate) return null;
  const days = Math.round((new Date(uploadedAt).getTime() - parseDay(readDate).getTime()) / 86_400_000);
  if (days > 60) return `讀到的日期比上傳早了 ${days} 天，年份或月份可能讀錯了。`;
  if (days < -1) return "讀到的日期在上傳之後，可能讀錯了。";
  return null;
}

/** A receipt's best name so far: what was read, or what it is waiting for. */
export function receiptTitle(receipt: ReceiptCard): string {
  return receipt.posting?.expense?.title || receipt.reading?.merchant || (receipt.state === "reading" ? "讀取中…" : "讀不出店家");
}

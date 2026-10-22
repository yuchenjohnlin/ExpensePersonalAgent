import { ReceiptIcon } from "lucide-react";
import { useSearchParams } from "react-router";

import { ReceiptListItem, UploadPanel, useReceipts, type ReceiptState } from "@/features/receipts";
import { Button } from "@/shared/ui/button";
import { EmptyState, Skeleton } from "@/shared/ui/feedback";
import { Tabs, TabsList, TabsTrigger } from "@/shared/ui/tabs";

const TABS: { value: "all" | ReceiptState; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "reading", label: "讀取中" },
  { value: "needs_review", label: "要看一下" },
  { value: "posted", label: "已入帳" },
];

/** Upload receipts, and see every receipt and where it stands. */
export function ReceiptsPage() {
  const [params, setParams] = useSearchParams();
  const tab = (TABS.find((option) => option.value === params.get("tab"))?.value ?? "all") as "all" | ReceiptState;
  const page = Math.max(1, Number(params.get("page")) || 1);
  const list = useReceipts(tab === "all" ? null : tab, page);
  const counts = list.data?.counts;
  const go = (next: Record<string, string | null>) =>
    setParams((old) => {
      const merged = new URLSearchParams(old);
      for (const [key, value] of Object.entries(next)) {
        if (value === null) merged.delete(key);
        else merged.set(key, value);
      }
      return merged;
    });

  return (
    <div className="grid gap-6">
      <header>
        <h1 className="text-2xl font-semibold">收據</h1>
        <p className="text-muted-foreground text-sm">拍照上傳就好：讀完會自動入帳，有疑問的放進「要看一下」。</p>
      </header>

      <UploadPanel />

      <section className="grid gap-3">
        <Tabs value={tab} onValueChange={(value) => go({ tab: value === "all" ? null : value, page: null })}>
          <TabsList className="w-full sm:w-fit">
            {TABS.map((option) => {
              const count = option.value === "reading" ? counts?.reading : option.value === "needs_review" ? counts?.needs_review : undefined;
              return (
                <TabsTrigger key={option.value} value={option.value} className="flex-1 sm:flex-none">
                  {option.label}
                  {count ? <span className="bg-background text-foreground rounded-full px-1.5 text-xs">{count}</span> : null}
                </TabsTrigger>
              );
            })}
          </TabsList>
        </Tabs>

        {list.isPending ? (
          <div className="grid gap-3 sm:grid-cols-2">{[0, 1, 2, 3].map((n) => <Skeleton key={n} className="h-24" />)}</div>
        ) : list.data?.receipts.length ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {list.data.receipts.map((receipt) => <ReceiptListItem key={receipt.id} receipt={receipt} />)}
          </div>
        ) : (
          <EmptyState icon={<ReceiptIcon />} title={tab === "all" ? "還沒有收據" : "這裡沒有收據"}>
            {tab === "all" ? "上面拍一張或選幾張照片就開始。" : null}
          </EmptyState>
        )}

        {list.data && list.data.pages > 1 ? (
          <div className="flex items-center justify-center gap-3 text-sm">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => go({ page: String(page - 1) })}>上一頁</Button>
            <span className="text-muted-foreground">{page} / {list.data.pages}</span>
            <Button variant="outline" size="sm" disabled={page >= list.data.pages} onClick={() => go({ page: String(page + 1) })}>下一頁</Button>
          </div>
        ) : null}
      </section>
    </div>
  );
}

import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { useToday } from "@/features/auth";
import { CategorySelect } from "@/features/ledger";
import { ApiError } from "@/shared/api/client";
import { Button } from "@/shared/ui/button";
import { Spinner } from "@/shared/ui/feedback";
import { Field, Input } from "@/shared/ui/input";

import { usePostByHand } from "./api";
import { dateDoubt } from "./status";
import type { ReceiptCard } from "./types";

/** Post a receipt that was set aside: what was read, checked and corrected by you. */
export function PostForm({ receipt }: { receipt: ReceiptCard }) {
  const reading = receipt.reading?.status === "succeeded" ? receipt.reading : null;
  const today = useToday();
  const [form, setForm] = useState({
    title: reading?.merchant ?? "", merchant: reading?.merchant ?? "", amount: reading?.amount ?? "",
    date: reading?.date ?? today, tax: reading?.tax ?? "", tip: "", receipt_discount: "",
  });
  const [category, setCategory] = useState<number | "">("");
  const [lines, setLines] = useState(Boolean(reading?.item_count));
  const post = usePostByHand();
  const error = post.error instanceof ApiError ? post.error : null;
  const set = (name: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setForm((old) => ({ ...old, [name]: event.target.value }));

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (category === "") return;
    post.mutate({
      id: receipt.id,
      input: { ...form, category_id: category, tax: form.tax.trim() || null, tip: form.tip.trim() || null,
        receipt_discount: form.receipt_discount.trim() || null, lines },
    }, { onSuccess: () => toast.success("已入帳") });
  }

  return (
    <form onSubmit={submit} className="grid gap-3 rounded-xl border bg-card p-4">
      <p className="font-medium">核對後入帳</p>
      {error && !Object.keys(error.fields).length ? <p className="text-destructive text-sm">{error.message}</p> : null}
      <div className="grid grid-cols-2 gap-3">
        <Field label="名稱" error={error?.field("title")} className="col-span-2">
          <Input value={form.title} onChange={set("title")} required maxLength={120} />
        </Field>
        <Field label="實付金額" error={error?.field("amount")}>
          <Input value={form.amount} onChange={set("amount")} inputMode="decimal" required className="money" />
        </Field>
        <Field label="日期" error={error?.field("date") ?? dateDoubt(form.date, receipt.created_at) ?? undefined}>
          <Input type="date" value={form.date} onChange={set("date")} required />
        </Field>
        <Field label="分類" error={error?.field("category_id")}>
          <CategorySelect value={category} onChange={setCategory} />
        </Field>
        <Field label="店家" error={error?.field("merchant")}>
          <Input value={form.merchant} onChange={set("merchant")} maxLength={120} />
        </Field>
        <Field label="稅" error={error?.field("tax")} hint="空白＝不知道">
          <Input value={form.tax} onChange={set("tax")} inputMode="decimal" className="money" />
        </Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="小費" error={error?.field("tip")}>
            <Input value={form.tip} onChange={set("tip")} inputMode="decimal" className="money" />
          </Field>
          <Field label="整張折扣" error={error?.field("receipt_discount")}>
            <Input value={form.receipt_discount} onChange={set("receipt_discount")} inputMode="decimal" className="money" />
          </Field>
        </div>
      </div>
      {reading?.item_count ? (
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={lines} onChange={(event) => setLines(event.target.checked)} className="accent-primary size-4" />
          同時把讀到的 {reading.item_count} 個品項建成明細
        </label>
      ) : null}
      <Button type="submit" disabled={post.isPending || category === ""}>
        {post.isPending ? <Spinner /> : null}
        入帳
      </Button>
    </form>
  );
}

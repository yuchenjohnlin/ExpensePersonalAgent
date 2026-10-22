import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { ExpenseDetail } from "@/features/ledger";
import type { ReceiptCard } from "@/features/receipts";
import { fakeServer, renderApp } from "@/test/render";

import { InboxPage } from "./InboxPage";

const expense: ExpenseDetail = {
  id: 2, title: "TRADER JOE'S", amount: "86.05", date: "2026-09-11", category: { id: 9, name: "未分類" },
  merchant: "TRADER JOE'S", notes: "", tax: "1.69", tip: "0.00", receipt_discount: "0.00", total_only: false,
  reviewed_at: null, line_count: 22, created_at: "2026-10-22T04:23:00Z", updated_at: "2026-10-22T04:24:45Z",
  lines: [], summary: { paid_total: "86.05", line_total: "84.36", line_discount_total: "0.00", net_total: "84.36",
    subtotal: "84.36", tax_rate: "0.020033", tip_rate: null, receipt_discount_rate: null, unrecorded: "0.00",
    unknown_amount_count: 0 },
};

const receipt: ReceiptCard = {
  id: 1, created_at: "2026-10-22T04:23:00Z", state: "posted", reasons: [],
  photos: [{ id: 1, position: 1, original_name: "tj.heic", preview_url: "/p", thumbnail_url: "/t", original_url: "/o" }],
  reading: { id: 1, status: "succeeded", provider: "vllm", model: "m", merchant: "TRADER JOE'S", date: "2026-09-11",
    amount: "86.05", tax: "1.69", item_count: 22, checks: [], error_code: "", error_message: "", elapsed_ms: 104000,
    completed_at: null, warnings: ["The transaction date '09-27-2026' conflicts with the printed date '09/11/2026'."] },
  posting: { mode: "auto", reading_id: 1, skipped: [], expense: null },
};

function serve() {
  return fakeServer({
    "GET /api/receipts": { body: { receipts: [], page: 1, pages: 1, total: 0, counts: { reading: 1, needs_review: 0 } } },
    "GET /api/expenses/unreviewed": { body: [expense] },
    "GET /api/receipts/for-expenses": { body: { receipts: { 2: receipt } } },
    "GET /api/categories": { body: [{ id: 1, name: "食材", system: false }, { id: 9, name: "未分類", system: true }] },
    "PATCH /api/expenses/2": (request) => ({ body: { ...expense, ...(request.body as object) } }),
  });
}

test("an auto-posted expense shows beside its photo, with the model's doubt about the date up front", async () => {
  serve();
  renderApp(<InboxPage />);
  expect(await screen.findByText("TRADER JOE'S")).toBeInTheDocument();
  expect(screen.getByText("$86.05")).toBeInTheDocument();
  expect(await screen.findByText("讀的時候日期有疑問，請對一下照片")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "看收據照片" })).toBeInTheDocument();
  expect(screen.getByText("1 張收據正在讀取，讀完會出現在下面，或直接入帳。")).toBeInTheDocument();
});

test("fixing the date and category saves at once; 看過了 marks it reviewed", async () => {
  const { sent } = serve();
  renderApp(<InboxPage />);
  fireEvent.change(await screen.findByLabelText("日期"), { target: { value: "2026-09-27" } });
  await waitFor(() => expect(sent.filter((r) => r.method === "PATCH").map((r) => r.body)).toEqual([{ date: "2026-09-27" }]));
  await userEvent.selectOptions(await screen.findByRole("combobox"), "1");
  await userEvent.click(screen.getByRole("button", { name: /看過了/ }));
  await waitFor(() => expect(sent.filter((r) => r.method === "PATCH").map((r) => r.body)).toEqual([
    { date: "2026-09-27" }, { category_id: 1 }, { reviewed: true }]));
});

test("with nothing waiting, the inbox says so", async () => {
  fakeServer({
    "GET /api/receipts": { body: { receipts: [], page: 1, pages: 1, total: 0, counts: { reading: 0, needs_review: 0 } } },
    "GET /api/expenses/unreviewed": { body: [] },
  });
  renderApp(<InboxPage />);
  expect(await screen.findByText("都處理好了")).toBeInTheDocument();
});

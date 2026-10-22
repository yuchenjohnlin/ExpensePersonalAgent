import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { ExpenseDetail } from "@/features/ledger";
import { fakeServer, renderApp } from "@/test/render";

import { CalendarPage } from "./CalendarPage";

const lunch: ExpenseDetail = {
  id: 2, title: "午餐", amount: "13.75", date: "2026-10-22", category: { id: 1, name: "外食" },
  merchant: "Chipotle", notes: "", tax: null, tip: "0.00", receipt_discount: "0.00", total_only: false,
  reviewed_at: "2026-10-22T12:00:00Z", line_count: 0, created_at: "2026-10-22T12:00:00Z", updated_at: "2026-10-22T12:00:00Z",
  lines: [], summary: { paid_total: "13.75", line_total: "0.00", line_discount_total: "0.00", net_total: "0.00",
    subtotal: "13.75", tax_rate: null, tip_rate: null, receipt_discount_rate: null, unrecorded: "13.75",
    unknown_amount_count: 0 },
};

function serve() {
  return fakeServer({
    "GET /api/calendar": { body: { month: "2026-10", today: "2026-10-22", total: "13.75",
      days: [{ date: "2026-10-22", total: "13.75", count: 1, merchants: ["Chipotle"] }] } },
    "GET /api/calendar/day": (request) => ({ body: request.path.endsWith("2026-10-22")
      ? { date: "2026-10-22", total: "13.75", expenses: [lunch] }
      : { date: request.path.slice(-10), total: "0.00", expenses: [] } }),
    "GET /api/categories": { body: [{ id: 1, name: "外食", system: false }, { id: 9, name: "未分類", system: true }] },
    "GET /api/receipts/for-expenses": { body: { receipts: {} } },
    "PATCH /api/expenses/2": (request) => ({ body: { ...lunch, ...(request.body as object) } }),
    "POST /api/expenses": (request) => ({ body: { ...lunch, id: 3, ...(request.body as object), category: { id: 1, name: "外食" } } }),
  });
}

const writes = (sent: ReturnType<typeof serve>["sent"]) =>
  sent.filter((request) => request.method !== "GET").map((request) => [request.method, request.path, request.body]);

test("the chosen day is a table: its week above, its expenses as rows, a new row at the end", async () => {
  serve();
  renderApp(<CalendarPage />, { route: "/calendar?day=2026-10-22" });
  expect(await screen.findByRole("heading", { name: "10月22日 週四" })).toBeInTheDocument();
  expect(await screen.findByDisplayValue("午餐")).toBeInTheDocument();
  expect(screen.getByText("1 筆，共 $13.75")).toBeInTheDocument();
  expect(await screen.findByRole("button", { name: "2026-10-22，支出 $13.75，Chipotle" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText("本週 $13.75")).toBeInTheDocument();
  expect(screen.getByLabelText("名稱，新增支出")).toHaveValue("");
});

test("leaving an edited cell saves that field; Enter on the new row adds it on the chosen day", async () => {
  const { sent } = serve();
  renderApp(<CalendarPage />, { route: "/calendar?day=2026-10-22" });
  const amount = await screen.findByLabelText("實付，午餐");
  await userEvent.clear(amount);
  await userEvent.type(amount, "14.00");
  await userEvent.tab();
  await waitFor(() => expect(writes(sent)).toEqual([["PATCH", "/api/expenses/2", { amount: "14.00" }]]));

  const title = screen.getByLabelText("名稱，新增支出");
  await userEvent.type(title, "咖啡");
  await userEvent.type(screen.getByLabelText("實付，新增支出"), "4.50");
  await userEvent.selectOptions(screen.getByLabelText("分類，新增支出"), "1");
  expect(writes(sent)).toHaveLength(1); // leaving the new row saves nothing
  await userEvent.keyboard("{Enter}");
  await waitFor(() => expect(writes(sent)[1]).toEqual(["POST", "/api/expenses",
    { title: "咖啡", amount: "4.50", date: "2026-10-22", merchant: "", notes: "", category_id: 1 }]));
  await waitFor(() => expect(screen.getByLabelText("名稱，新增支出")).toHaveValue(""));
  expect(screen.getByLabelText("名稱，新增支出")).toHaveFocus(); // keep typing the next one
});

test("choosing another day asks first when a new row is half typed", async () => {
  serve();
  renderApp(<CalendarPage />, { route: "/calendar?day=2026-10-22" });
  await userEvent.type(await screen.findByLabelText("名稱，新增支出"), "半打的");
  const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);

  await userEvent.click(screen.getByRole("button", { name: "2026-10-23，無支出" }));
  expect(confirm).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("heading", { name: "10月22日 週四" })).toBeInTheDocument();
  expect(screen.getByLabelText("名稱，新增支出")).toHaveValue("半打的");

  await userEvent.click(screen.getByRole("button", { name: "2026-10-23，無支出" }));
  expect(await screen.findByRole("heading", { name: "10月23日 週五" })).toBeInTheDocument();
  expect(await screen.findByText("還沒有支出")).toBeInTheDocument();
  expect(screen.getByLabelText("名稱，新增支出")).toHaveValue("");
  confirm.mockRestore();
});

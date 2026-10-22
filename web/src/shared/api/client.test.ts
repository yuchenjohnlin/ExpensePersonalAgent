import { fakeServer } from "@/test/render";

import { api, ApiError, onSignedOut, setCsrfToken } from "./client";

test("writes carry the CSRF token and JSON; reads do not", async () => {
  const { sent } = fakeServer({ "GET /api/x": { body: { ok: 1 } }, "PATCH /api/x": { body: { ok: 2 } } });
  setCsrfToken("abc");
  expect(await api.get("/api/x")).toEqual({ ok: 1 });
  expect(await api.patch("/api/x", { title: "a" })).toEqual({ ok: 2 });
  expect(sent[0].headers["X-CSRF-Token"]).toBeUndefined();
  expect(sent[1].headers).toMatchObject({ "X-CSRF-Token": "abc", "Content-Type": "application/json" });
  expect(sent[1].body).toEqual({ title: "a" });
});

test("an error answer becomes an ApiError with its fields", async () => {
  fakeServer({ "POST /api/x": { status: 400, body: { error: "請檢查輸入內容。", fields: { amount: ["金額必須大於 0。"] } } } });
  const error = (await api.post("/api/x", {}).catch((e: unknown) => e)) as ApiError;
  expect(error).toBeInstanceOf(ApiError);
  expect([error.status, error.message, error.field("amount")]).toEqual([400, "請檢查輸入內容。", "金額必須大於 0。"]);
});

test("a 401 tells the app the session ended", async () => {
  fakeServer({ "GET /api/x": { status: 401, body: { error: "請先登入。" } } });
  const ended = vi.fn();
  onSignedOut(ended);
  await expect(api.get("/api/x")).rejects.toBeInstanceOf(ApiError);
  expect(ended).toHaveBeenCalledOnce();
});

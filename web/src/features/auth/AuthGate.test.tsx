import { QueryClient } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";

import { Providers } from "@/app/providers";
import { fakeServer, SESSION } from "@/test/render";

import { AuthGate } from "./AuthGate";

function renderGate() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<Providers client={client}><MemoryRouter><AuthGate><p>the app</p></AuthGate></MemoryRouter></Providers>);
}

test("signed out, only the sign-in page shows; signing in opens the app with the new CSRF token", async () => {
  const { sent } = fakeServer({
    "GET /api/session": { body: { ...SESSION, user: null, csrf_token: "before" } },
    "POST /api/auth/login": { body: { ...SESSION, csrf_token: "after" } },
  });
  renderGate();
  await userEvent.type(await screen.findByLabelText("帳號"), "yuchen");
  await userEvent.type(screen.getByLabelText("密碼"), "a password");
  expect(screen.queryByText("the app")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "登入" }));
  expect(await screen.findByText("the app")).toBeInTheDocument();
  const login = sent.find((request) => request.method === "POST")!;
  expect(login.headers["X-CSRF-Token"]).toBe("before");
  expect(login.body).toEqual({ username: "yuchen", password: "a password" });
});

test("a wrong password says so on the form", async () => {
  fakeServer({
    "GET /api/session": { body: { ...SESSION, user: null } },
    "POST /api/auth/login": { status: 400, body: { error: "請檢查輸入內容。", fields: { __all__: ["帳號或密碼不正確。"] } } },
  });
  renderGate();
  await userEvent.type(await screen.findByLabelText("帳號"), "yuchen");
  await userEvent.type(screen.getByLabelText("密碼"), "wrong");
  await userEvent.click(screen.getByRole("button", { name: "登入" }));
  await waitFor(() => expect(screen.getByText("帳號或密碼不正確。")).toBeInTheDocument());
});

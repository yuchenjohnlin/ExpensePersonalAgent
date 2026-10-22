/** Rendering a piece of the app in a test: the real providers and router, and a fake fetch that
 * answers by "METHOD /path" and remembers every request. */
import { QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type * as React from "react";
import { MemoryRouter } from "react-router";

import { Providers } from "@/app/providers";
import { setCsrfToken } from "@/shared/api/client";

type Answer = { status?: number; body: unknown } | ((request: Sent) => { status?: number; body: unknown });
export type Sent = { method: string; path: string; headers: Record<string, string>; body: unknown };

export function fakeServer(routes: Record<string, Answer>) {
  const sent: Sent[] = [];
  const fetch = vi.fn(async (input: string, init: RequestInit = {}) => {
    const method = init.method ?? "GET";
    const path = String(input);
    const body = init.body instanceof FormData ? init.body : init.body ? JSON.parse(String(init.body)) : undefined;
    const request = { method, path, headers: (init.headers ?? {}) as Record<string, string>, body };
    sent.push(request);
    const key = `${method} ${path.split("?")[0]}`;
    const route = routes[`${method} ${path}`] ?? routes[key];
    if (!route) return new Response(JSON.stringify({ error: `no route for ${key}` }), { status: 404 });
    const answer = typeof route === "function" ? route(request) : route;
    return new Response(JSON.stringify(answer.body), { status: answer.status ?? 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetch);
  return { sent, fetch };
}

export const SESSION = {
  csrf_token: "token-1", user: { id: "u1", username: "yuchen" }, today: "2026-10-22",
  timezone: "America/New_York", currency: "USD",
};

export function renderApp(ui: React.ReactNode, { route = "/" } = {}) {
  setCsrfToken(SESSION.csrf_token);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  client.setQueryData(["session"], SESSION);
  return render(
    <Providers client={client}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </Providers>,
  );
}

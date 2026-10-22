/** The only code that calls fetch. Every feature's api.ts goes through here, so the CSRF token,
 * JSON, and the error shape ({"error", "fields"}) are handled once.
 *
 * The server keeps the session in an HttpOnly cookie the page never sees. Writes must send the
 * CSRF token from GET /api/session in X-CSRF-Token (features/auth keeps it current here). A 401
 * means the session ended: the registered handler sends the app back to the sign-in page. */

export class ApiError extends Error {
  status: number;
  fields: Record<string, string[]>;
  body: Record<string, unknown>;

  constructor(status: number, body: unknown) {
    const data = (body && typeof body === "object" ? body : {}) as Record<string, unknown>;
    super(typeof data.error === "string" ? data.error : "伺服器暫時沒有回應，請稍後再試。");
    this.status = status;
    this.body = data;
    this.fields = (data.fields as Record<string, string[]>) ?? {};
  }

  /** The first message for a field, for showing under that input. */
  field(name: string): string | undefined {
    return this.fields[name]?.[0];
  }
}

let csrfToken = "";
let signedOut: () => void = () => {};

export function setCsrfToken(token: string) {
  csrfToken = token;
}

export function onSignedOut(handler: () => void) {
  signedOut = handler;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body; // the browser sets the multipart boundary
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let response: Response;
  try {
    response = await fetch(path, { method, headers, body: payload, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, { error: "連不上伺服器，請確認網路後再試。" });
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) signedOut();
    throw new ApiError(response.status, data);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),
};

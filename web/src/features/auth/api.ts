/** The only code that calls the server's auth module (/api/session, /api/auth/*). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, setCsrfToken } from "@/shared/api/client";

export type Session = {
  csrf_token: string;
  user: { id: string; username: string } | null; // null until signed in
  today: string; // the ledger's today, "YYYY-MM-DD"
  timezone: string;
  currency: string;
};

export const sessionKey = ["session"] as const;

async function fetchSession(): Promise<Session> {
  const session = await api.get<Session>("/api/session");
  setCsrfToken(session.csrf_token);
  return session;
}

export function useSession() {
  return useQuery({ queryKey: sessionKey, queryFn: fetchSession, staleTime: Infinity });
}

/** The ledger's today; only used inside the signed-in app, where the session is loaded. */
export function useToday(): string {
  return useSession().data?.today ?? new Date().toISOString().slice(0, 10);
}

export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { username: string; password: string }) => api.post<Session>("/api/auth/login", body),
    onSuccess: (session) => {
      setCsrfToken(session.csrf_token); // signing in rotates it
      client.removeQueries({ predicate: (query) => query.queryKey[0] !== sessionKey[0] });
      client.setQueryData(sessionKey, session);
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<Session>("/api/auth/logout"),
    onSuccess: (session) => {
      setCsrfToken(session.csrf_token);
      client.clear(); // nothing of the last account stays in memory
      client.setQueryData(sessionKey, session);
    },
  });
}

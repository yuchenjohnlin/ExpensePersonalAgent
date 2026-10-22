import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { Toaster } from "sonner";

import { sessionKey } from "@/features/auth";
import { ApiError, onSignedOut } from "@/shared/api/client";

export function makeQueryClient() {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        // Ask again on a network or server failure, not on "not found" or "not allowed".
        retry: (count, error) => count < 2 && !(error instanceof ApiError && error.status >= 400 && error.status < 500),
      },
    },
  });
  // A 401 anywhere: the session ended. Reload it, and the AuthGate shows the sign-in page.
  onSignedOut(() => client.invalidateQueries({ queryKey: sessionKey }));
  return client;
}

export function Providers({ children, client }: { children: React.ReactNode; client?: QueryClient }) {
  const [queryClient] = useState(() => client ?? makeQueryClient());
  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <Toaster position="top-center" richColors closeButton />
    </QueryClientProvider>
  );
}

import type * as React from "react";

import { Button } from "@/shared/ui/button";
import { Spinner } from "@/shared/ui/feedback";

import { useSession } from "./api";
import { SignInPage } from "./SignInPage";

/** Shows the app only to a signed-in account; otherwise the sign-in page. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const session = useSession();
  if (session.isPending) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <Spinner className="text-muted-foreground size-6" />
      </div>
    );
  }
  if (session.isError) {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-3 px-4 text-center">
        <p>連不上伺服器。</p>
        <Button variant="outline" onClick={() => session.refetch()}>再試一次</Button>
      </div>
    );
  }
  if (!session.data.user) return <SignInPage />;
  return children;
}

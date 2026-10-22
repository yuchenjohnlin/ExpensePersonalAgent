import { useState } from "react";

import { ApiError } from "@/shared/api/client";
import { Button } from "@/shared/ui/button";
import { Card, CardContent } from "@/shared/ui/card";
import { Notice, Spinner } from "@/shared/ui/feedback";
import { Field, Input } from "@/shared/ui/input";

import { useLogin } from "./api";

export function SignInPage() {
  const login = useLogin();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const error = login.error instanceof ApiError ? login.error : null;

  return (
    <main className="flex min-h-dvh items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <img src="/favicon.svg" alt="" className="size-12" />
          <div>
            <h1 className="text-2xl font-semibold">CojiDaily</h1>
            <p className="text-muted-foreground text-sm">拍下收據，帳就記好了。</p>
          </div>
        </div>
        <Card>
          <CardContent>
            <form
              className="grid gap-4"
              onSubmit={(event) => {
                event.preventDefault();
                login.mutate({ username, password });
              }}
            >
              {error ? <Notice tone="destructive">{error.field("__all__") ?? error.message}</Notice> : null}
              <Field label="帳號">
                <Input autoComplete="username" autoFocus value={username} onChange={(e) => setUsername(e.target.value)} required />
              </Field>
              <Field label="密碼">
                <Input type="password" autoComplete="current-password" value={password}
                  onChange={(e) => setPassword(e.target.value)} required />
              </Field>
              <Button type="submit" size="lg" disabled={login.isPending}>
                {login.isPending ? <Spinner /> : null}
                登入
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}

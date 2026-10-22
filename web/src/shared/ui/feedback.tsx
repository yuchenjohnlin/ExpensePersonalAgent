import { Loader2Icon } from "lucide-react";
import type * as React from "react";

import { cn } from "@/shared/lib/utils";

/** Small pieces for waiting, nothing-here and problems. */

function Spinner({ className }: { className?: string }) {
  return <Loader2Icon aria-hidden className={cn("size-4 animate-spin", className)} />;
}

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} {...props} />;
}

function EmptyState({ icon, title, children, className }: {
  icon?: React.ReactNode; title: React.ReactNode; children?: React.ReactNode; className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center gap-2 rounded-xl border border-dashed px-6 py-10 text-center", className)}>
      {icon ? <div className="text-muted-foreground [&_svg]:size-8">{icon}</div> : null}
      <p className="font-medium">{title}</p>
      {children ? <div className="text-muted-foreground max-w-sm text-sm">{children}</div> : null}
    </div>
  );
}

function Notice({ tone = "warning", icon, children, className }: {
  tone?: "warning" | "info" | "success" | "destructive"; icon?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
  const tones = {
    warning: "bg-warning text-warning-foreground",
    info: "bg-info text-info-foreground",
    success: "bg-success text-success-foreground",
    destructive: "bg-destructive/10 text-destructive",
  };
  return (
    <div role="status" className={cn("flex gap-2 rounded-lg px-3 py-2.5 text-sm [&_svg]:mt-0.5 [&_svg]:size-4 [&_svg]:shrink-0", tones[tone], className)}>
      {icon}
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

export { EmptyState, Notice, Skeleton, Spinner };

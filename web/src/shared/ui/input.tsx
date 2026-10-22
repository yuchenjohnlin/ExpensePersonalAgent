import { cloneElement, isValidElement, useId } from "react";
import type * as React from "react";

import { cn } from "@/shared/lib/utils";

const field =
  "w-full min-w-0 rounded-md border border-input bg-card px-3 text-base shadow-xs transition-[color,box-shadow] outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 md:text-sm";

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return <input type={type} data-slot="input" className={cn(field, "h-9 py-1", className)} {...props} />;
}

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return <textarea data-slot="textarea" className={cn(field, "min-h-16 py-2", className)} {...props} />;
}

/** The browser's own select, styled: on a phone it opens the system picker. */
function NativeSelect({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      data-slot="select"
      className={cn(field, "h-9 cursor-pointer appearance-none bg-[length:16px] bg-[right_0.5rem_center] bg-no-repeat pr-8", className)}
      style={{
        backgroundImage:
          "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23888' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")",
      }}
      {...props}
    />
  );
}

function Label({ className, ...props }: React.ComponentProps<"label">) {
  return <label data-slot="label" className={cn("text-sm font-medium leading-none select-none", className)} {...props} />;
}

/** A label, the input, and the field's error under it. The label is tied to the input (screen
 * readers say it, a tap on it focuses the input), and an error marks the input invalid. */
function Field({ label, error, hint, children, className }: {
  label: React.ReactNode; error?: string; hint?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
  const generated = useId();
  const element = isValidElement<{ id?: string; "aria-invalid"?: boolean }>(children) ? children : null;
  const id = element?.props.id ?? generated;
  return (
    <div className={cn("grid gap-1.5", className)}>
      <Label htmlFor={element ? id : undefined}>{label}</Label>
      {element ? cloneElement(element, { id, "aria-invalid": error ? true : element.props["aria-invalid"] }) : children}
      {error ? <p className="text-destructive text-xs">{error}</p> : hint ? <p className="text-muted-foreground text-xs">{hint}</p> : null}
    </div>
  );
}

export { Field, Input, Label, NativeSelect, Textarea };

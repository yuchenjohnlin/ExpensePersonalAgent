import { XIcon } from "lucide-react";
import { Dialog as SheetPrimitive } from "radix-ui";
import type * as React from "react";

import { cn } from "@/shared/lib/utils";

/** A panel that slides in from the right (full width on a phone), for looking at one thing in
 * detail without leaving the page under it. Same accessibility as Dialog. */
const Sheet = SheetPrimitive.Root;

function SheetContent({ className, children, ...props }: React.ComponentProps<typeof SheetPrimitive.Content>) {
  return (
    <SheetPrimitive.Portal>
      <SheetPrimitive.Overlay className="fixed inset-0 z-50 bg-black/40 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0" />
      <SheetPrimitive.Content
        className={cn(
          "fixed inset-y-0 right-0 z-50 flex h-full w-full flex-col bg-background shadow-xl transition ease-in-out sm:max-w-xl data-[state=open]:animate-in data-[state=open]:slide-in-from-right data-[state=open]:duration-300 data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right data-[state=closed]:duration-200",
          className,
        )}
        {...props}
      >
        {children}
        <SheetPrimitive.Close className="absolute top-4 right-4 rounded-full bg-background/80 p-1.5 opacity-80 backdrop-blur transition-opacity hover:opacity-100 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none [&_svg]:size-5">
          <XIcon />
          <span className="sr-only">關閉</span>
        </SheetPrimitive.Close>
      </SheetPrimitive.Content>
    </SheetPrimitive.Portal>
  );
}

const SheetTitle = SheetPrimitive.Title;
const SheetDescription = SheetPrimitive.Description;

export { Sheet, SheetContent, SheetDescription, SheetTitle };

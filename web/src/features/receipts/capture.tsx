import { CameraIcon } from "lucide-react";
import { createContext, useContext, useRef, useState } from "react";
import type * as React from "react";
import { useNavigate } from "react-router";

import { cn } from "@/shared/lib/utils";

/** Photos taken with the camera button in the navigation, on their way to the upload panel.
 * The button has to open the camera itself (browsers only open it from a tap), so it keeps what
 * was shot here and goes to the receipts page, where UploadPanel picks them up. */
type Pending = { files: File[]; give: (files: File[]) => void; take: () => File[] };

const PendingPhotos = createContext<Pending | null>(null);

export function PendingPhotosProvider({ children }: { children: React.ReactNode }) {
  const [files, setFiles] = useState<File[]>([]);
  const value: Pending = {
    files,
    give: (more) => setFiles((old) => [...old, ...more]),
    take: () => {
      const taken = files;
      setFiles([]);
      return taken;
    },
  };
  return <PendingPhotos.Provider value={value}>{children}</PendingPhotos.Provider>;
}

export function usePendingPhotos(): Pending {
  return useContext(PendingPhotos) ?? { files: [], give: () => {}, take: () => [] };
}

export function CaptureButton({ className, label = "拍收據" }: { className?: string; label?: string }) {
  const input = useRef<HTMLInputElement>(null);
  const pending = usePendingPhotos();
  const navigate = useNavigate();
  return (
    <>
      <input ref={input} type="file" accept="image/*" capture="environment" hidden
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          event.target.value = "";
          if (!files.length) return;
          pending.give(files);
          navigate("/receipts");
        }} />
      <button type="button" onClick={() => input.current?.click()} aria-label={label}
        className={cn("flex items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition-transform active:scale-95", className)}>
        <CameraIcon className="size-6" />
      </button>
    </>
  );
}

import { CameraIcon, ImageIcon, ImagePlusIcon, Link2Icon, Unlink2Icon, UploadIcon, XIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/shared/api/client";
import { cn } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/shared/ui/dialog";
import { Spinner } from "@/shared/ui/feedback";

import { useUpload } from "./api";
import { usePendingPhotos } from "./capture";
import { groupsFrom, MAX_PHOTOS_PER_RECEIPT, MAX_PHOTOS_PER_UPLOAD } from "./grouping";
import type { Duplicate } from "./types";

type Picked = { file: File; url: string; joins: boolean };
const ACCEPT = "image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif";

/** Pick or shoot photos, say which belong to the same receipt, upload. Each receipt is then read
 * in the background; nothing here waits for the model. */
export function UploadPanel() {
  const [picked, setPicked] = useState<Picked[]>([]);
  const [duplicates, setDuplicates] = useState<Duplicate[] | null>(null);
  const [dragging, setDragging] = useState(false);
  const upload = useUpload();
  const chooser = useRef<HTMLInputElement>(null);
  const camera = useRef<HTMLInputElement>(null);
  const groups = groupsFrom(picked.map((photo) => photo.joins));

  // Photos shot with the navigation's camera button arrive here.
  const pending = usePendingPhotos();
  useEffect(() => {
    if (pending.files.length) add(pending.take());
  }, [pending.files]); // only when photos arrive; add and take are new each render

  function add(files: FileList | File[] | null) {
    const images = Array.from(files ?? []).filter((file) => file.type.startsWith("image/") || /\.hei[cf]$/i.test(file.name));
    if (!images.length) return;
    setPicked((old) => {
      const room = MAX_PHOTOS_PER_UPLOAD - old.length;
      if (images.length > room) toast.warning(`一次最多 ${MAX_PHOTOS_PER_UPLOAD} 張照片，多的沒有加進來。`);
      return [...old, ...images.slice(0, Math.max(room, 0)).map((file) => ({ file, url: URL.createObjectURL(file), joins: false }))];
    });
  }

  function clear() {
    picked.forEach((photo) => URL.revokeObjectURL(photo.url));
    setPicked([]);
  }

  function toggleJoin(index: number) {
    setPicked((old) => old.map((photo, at) => (at === index ? { ...photo, joins: !photo.joins } : photo)));
  }

  function remove(index: number) {
    setPicked((old) => {
      URL.revokeObjectURL(old[index].url);
      const next = old.filter((_, at) => at !== index);
      if (next.length && index === 0) next[0] = { ...next[0], joins: false };
      return next;
    });
  }

  function send(allowDuplicates = false) {
    if (groups.some((group) => group.length > MAX_PHOTOS_PER_RECEIPT)) {
      toast.error(`一張收據最多 ${MAX_PHOTOS_PER_RECEIPT} 張照片。`);
      return;
    }
    upload.mutate({ files: picked.map((photo) => photo.file), groups, allowDuplicates }, {
      onSuccess: ({ receipts }) => {
        setDuplicates(null);
        clear();
        toast.success(`已上傳 ${receipts.length} 張收據，正在背景讀取。`, { description: "讀完會自動入帳，或放進「要看一下」。" });
      },
      onError: (error) => {
        if (error instanceof ApiError && error.status === 409) setDuplicates(error.body.duplicates as Duplicate[]);
        else toast.error(error instanceof ApiError ? (error.field("photos") ?? error.message) : "上傳失敗。");
      },
    });
  }

  const inputs = (
    <>
      <input ref={chooser} type="file" accept={ACCEPT} multiple hidden onChange={(event) => { add(event.target.files); event.target.value = ""; }} />
      <input ref={camera} type="file" accept="image/*" capture="environment" hidden onChange={(event) => { add(event.target.files); event.target.value = ""; }} />
    </>
  );

  if (!picked.length) {
    return (
      <div
        onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => { event.preventDefault(); setDragging(false); add(event.dataTransfer.files); }}
        className={cn("flex flex-col items-center gap-3 rounded-xl border-2 border-dashed bg-card px-6 py-8 text-center transition-colors",
          dragging && "border-primary bg-accent")}
      >
        {inputs}
        <div className="bg-accent text-accent-foreground rounded-full p-3"><ImagePlusIcon className="size-6" /></div>
        <div>
          <p className="font-medium">拍收據，或選幾張照片</p>
          <p className="text-muted-foreground text-sm">也可以把照片拖進來。上傳後會在背景讀取，不用等。</p>
        </div>
        <div className="flex flex-wrap justify-center gap-2">
          <Button onClick={() => camera.current?.click()}><CameraIcon /> 拍照</Button>
          <Button variant="outline" onClick={() => chooser.current?.click()}><ImageIcon /> 選擇照片</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border bg-card p-4 shadow-xs">
      {inputs}
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <p className="font-medium">{picked.length} 張照片 → {groups.length} 張收據</p>
        <p className="text-muted-foreground hidden text-xs sm:block">長收據分兩張拍？在第二張按「併到上一張」。</p>
      </div>
      <ol className="grid gap-3">
        {groups.map((group, number) => (
          <li key={group[0]} className="rounded-lg border bg-muted/30 p-2">
            <p className="text-muted-foreground mb-2 px-1 text-xs">收據 {number + 1}{group.length > 1 ? `（${group.length} 張照片）` : ""}</p>
            <div className="flex flex-wrap gap-2">
              {group.map((index) => (
                <PhotoTile key={picked[index].url} photo={picked[index]} index={index}
                  onToggleJoin={() => toggleJoin(index)} onRemove={() => remove(index)} />
              ))}
            </div>
          </li>
        ))}
      </ol>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => chooser.current?.click()}><ImagePlusIcon /> 再加照片</Button>
        <Button variant="outline" size="sm" onClick={() => camera.current?.click()} className="sm:hidden"><CameraIcon /> 拍照</Button>
        <Button variant="ghost" size="sm" onClick={clear} disabled={upload.isPending}>清除</Button>
        <Button className="ml-auto" onClick={() => send()} disabled={upload.isPending}>
          {upload.isPending ? <Spinner /> : <UploadIcon />}
          上傳 {groups.length} 張收據
        </Button>
      </div>
      <Dialog open={duplicates !== null} onOpenChange={(open) => !open && setDuplicates(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>有照片之前上傳過</DialogTitle>
            <DialogDescription>
              {duplicates?.length} 張照片和已經存的（或這次選了兩次的）一模一樣。確定是不同的收據才需要再上傳。
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-wrap gap-2">
            {duplicates?.map((duplicate) => (
              <img key={duplicate.index} src={picked[duplicate.index]?.url} alt="" className="size-16 rounded-md border object-cover" />
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDuplicates(null)}>先不要</Button>
            <Button onClick={() => send(true)} disabled={upload.isPending}>
              {upload.isPending ? <Spinner /> : null}
              仍要上傳
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function PhotoTile({ photo, index, onToggleJoin, onRemove }: {
  photo: Picked; index: number; onToggleJoin: () => void; onRemove: () => void;
}) {
  const [broken, setBroken] = useState(false); // a HEIC this browser cannot draw
  return (
    <figure className="relative w-24">
      {broken ? (
        <div className="text-muted-foreground flex size-24 flex-col items-center justify-center gap-1 rounded-md border bg-card p-1 text-center text-[10px] break-all">
          <ImageIcon className="size-5" />{photo.file.name}
        </div>
      ) : (
        <img src={photo.url} alt={photo.file.name} onError={() => setBroken(true)} className="size-24 rounded-md border object-cover" />
      )}
      <button type="button" onClick={onRemove} aria-label={`移除 ${photo.file.name}`}
        className="absolute -top-1.5 -right-1.5 rounded-full border bg-card p-0.5 shadow-sm hover:bg-accent">
        <XIcon className="size-3.5" />
      </button>
      {index > 0 ? (
        <button type="button" onClick={onToggleJoin}
          className="text-muted-foreground hover:text-foreground mt-1 flex w-full items-center justify-center gap-1 text-[11px]">
          {photo.joins ? <><Unlink2Icon className="size-3" /> 拆成另一張</> : <><Link2Icon className="size-3" /> 併到上一張</>}
        </button>
      ) : null}
    </figure>
  );
}

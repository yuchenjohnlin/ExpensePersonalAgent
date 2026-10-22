import { cn } from "@/shared/lib/utils";
import { NativeSelect } from "@/shared/ui/input";

import { useCategories } from "./api";

// One color per default category, so a list of expenses reads at a glance.
const COLORS: Record<string, string> = {
  食材: "bg-emerald-500",
  外食: "bg-orange-500",
  生活用品: "bg-sky-500",
  交通: "bg-violet-500",
  保險: "bg-slate-500",
  訂閱: "bg-pink-500",
  娛樂: "bg-amber-500",
  其他: "bg-stone-400",
};

export function CategoryDot({ name, className }: { name: string; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("inline-block size-2.5 shrink-0 rounded-full", COLORS[name] ?? "border border-dashed border-muted-foreground bg-transparent", className)}
    />
  );
}

/** The owner's categories; `value` is a category id, or "" for none chosen yet. */
export function CategorySelect({ value, onChange, className, id, invalid, placeholder = "選擇分類" }: {
  value: number | ""; onChange: (id: number) => void; className?: string; id?: string; invalid?: boolean; placeholder?: string;
}) {
  const categories = useCategories();
  return (
    <NativeSelect id={id} className={className} value={value} aria-invalid={invalid || undefined}
      onChange={(event) => onChange(Number(event.target.value))}>
      {value === "" ? <option value="" disabled>{placeholder}</option> : null}
      {(categories.data ?? []).map((category) => (
        <option key={category.id} value={category.id}>{category.name}</option>
      ))}
    </NativeSelect>
  );
}

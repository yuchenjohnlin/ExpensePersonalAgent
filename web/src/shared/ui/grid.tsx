/** Tables you edit in place (pm/decisions/inline-grid-autosave.md), moved from the old frontend's
 * InlineGrid.tsx with the same rules:
 *
 * - A cell reads like text; hovering shows a faint frame; clicking edits it where it is. Nothing pops up.
 * - A saved row saves when you leave a cell (or press Enter). No timer. One cell may hold several
 *   controls (a number and its unit): moving between them is not leaving.
 * - Esc puts the cell back. One request per row at a time; what you type meanwhile is sent after.
 * - A failed save keeps your edits and says why under the row; the same edits are not resent on
 *   every move, only after a change or Enter.
 * - The last row is new: leaving it saves nothing; Enter or its button creates it.
 * - The page knows which rows hold edits that would be lost, and asks before switching away.
 */
import { CheckIcon, PlusIcon } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type * as React from "react";

import { ApiError } from "@/shared/api/client";
import { cn } from "@/shared/lib/utils";

import { Spinner } from "./feedback";

export type Values = Record<string, string>;
export type FieldErrors = Record<string, string[]>;
export type RowStatus = "idle" | "saving" | "saved" | "error";

export type GridRow<T extends Values> = {
  value: T; // what the row shows: the saved values with unsaved edits on top
  dirty: boolean;
  status: RowStatus;
  error: string;
  fields: FieldErrors;
  creating: boolean;
  atRisk: boolean; // edits that would be lost: a new row with input, or edits that failed to save
  set: (key: keyof T & string, text: string) => void;
  revert: (keys: (keyof T & string)[]) => void;
  leave: () => void;
  submit: () => void;
};

type Options = {
  create?: boolean;
  // A save that fails after the row is gone (day switched, row collapsed) has nowhere to show.
  onLost?: (message: string) => void;
};

const without = <T extends Values>(edits: Partial<T>, done: (key: string, text: string) => boolean) =>
  Object.fromEntries(Object.entries(edits).filter(([key, text]) => !done(key, text as string))) as Partial<T>;

/** `save` gets the whole row and the changed fields; for a saved row it resolves to the values
 * as now stored (the server may normalise or work some out), which become the row's new base. */
export function useGridRow<T extends Values>(
  saved: T,
  save: (next: T, changed: Partial<T>) => Promise<T | void>,
  { create = false, onLost }: Options = {},
): GridRow<T> {
  const [, rerender] = useState(0);
  const refresh = () => rerender((n) => n + 1);
  const base = useRef(saved);
  const seen = useRef(JSON.stringify(saved));
  const key = JSON.stringify(saved);
  if (seen.current !== key) { // a reload replaces what the row is saved as; edits stay on top
    seen.current = key;
    base.current = saved;
  }
  const edits = useRef<Partial<T>>({});
  const saveRef = useRef(save);
  saveRef.current = save;
  const lostRef = useRef(onLost);
  lostRef.current = onLost;
  const [status, setStatus] = useState<RowStatus>("idle");
  const [error, setError] = useState("");
  const [fields, setFields] = useState<FieldErrors>({});
  const flight = useRef(false);
  const again = useRef(false);
  const failed = useRef(""); // edits that already failed are not resent on every move
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  const dirty = Object.keys(edits.current).length > 0;
  useDraftWarning(dirty || status === "saving");

  const commit = async (force: boolean): Promise<void> => {
    const pending = edits.current;
    if (!Object.keys(pending).length) return;
    const attempt = JSON.stringify(pending);
    if (!force && failed.current === attempt) return;
    if (flight.current) {
      again.current = true;
      return;
    }
    flight.current = true;
    setStatus("saving");
    setError("");
    setFields({});
    try {
      const stored = await saveRef.current({ ...base.current, ...pending } as T, pending);
      failed.current = "";
      if (create) edits.current = {};
      else {
        if (stored) base.current = stored;
        // Keep only what was typed while this save was on its way.
        edits.current = without(edits.current, (field, text) => text === pending[field] || text === base.current[field]);
      }
      if (mounted.current) setStatus(create ? "idle" : "saved");
    } catch (problem) {
      failed.current = attempt;
      const message = problem instanceof Error ? problem.message : "儲存失敗，輸入已保留。";
      if (mounted.current) {
        setStatus("error");
        setError(message);
        setFields(problem instanceof ApiError ? problem.fields : {});
      } else lostRef.current?.(message);
    } finally {
      flight.current = false;
      if (mounted.current) refresh();
      if (again.current) {
        again.current = false;
        void commit(false);
      }
    }
  };

  return {
    value: { ...base.current, ...edits.current } as T,
    dirty,
    status,
    error,
    fields,
    creating: create,
    atRisk: create ? dirty : status === "error" && dirty,
    set: (field, text) => {
      edits.current = text === base.current[field]
        ? without(edits.current, (name) => name === field)
        : { ...edits.current, [field]: text };
      refresh();
    },
    revert: (keys) => {
      edits.current = without(edits.current, (name) => keys.includes(name));
      failed.current = "";
      if (!Object.keys(edits.current).length) {
        setStatus("idle");
        setError("");
        setFields({});
      } else setFields((current) => without(current as unknown as Values, (name) => keys.includes(name)) as unknown as FieldErrors);
      refresh();
    },
    leave: () => { if (!create) void commit(false); },
    submit: () => void commit(true),
  };
}

/** Leaving the cell saves, Enter saves now, Esc puts the cell back; an Enter that confirms an IME
 * candidate (typing Chinese) does nothing. */
export function cellHandlers<T extends Values>(row: GridRow<T>, keys: (keyof T & string)[]) {
  return {
    onBlur: (event: React.FocusEvent<HTMLElement>) => {
      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) row.leave();
    },
    onKeyDown: (event: React.KeyboardEvent<HTMLElement>) => {
      if (event.nativeEvent.isComposing || event.keyCode === 229) {
        if (event.key === "Enter") event.preventDefault();
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        row.submit();
      } else if (event.key === "Escape") {
        event.preventDefault();
        row.revert(keys);
      }
    },
  };
}

/** One cell, which may hold several controls (an amount and its unit). */
export function GridCell<T extends Values>({ row, keys, className, children }: {
  row: GridRow<T>; keys: (keyof T & string)[]; className?: string; children: React.ReactNode;
}) {
  const problems = keys.flatMap((name) => row.fields[name] ?? []);
  return (
    <div {...cellHandlers(row, keys)} title={problems.join(" ") || undefined}
      className={cn(
        "flex min-h-8 items-center rounded-md border border-transparent transition-colors hover:border-border",
        "focus-within:border-ring focus-within:bg-card focus-within:ring-2 focus-within:ring-ring/25",
        problems.length && "border-destructive/60 bg-destructive/5",
        // the controls inside: borderless, transparent, the cell draws the frame
        "[&_input]:min-h-8 [&_input]:w-full [&_input]:min-w-0 [&_input]:bg-transparent [&_input]:px-2 [&_input]:outline-none",
        "[&_input]:placeholder:text-muted-foreground/60 [&_input.derived]:placeholder:text-muted-foreground [&_input.derived]:placeholder:italic",
        "[&_select]:h-8 [&_select]:shrink-0 [&_select]:cursor-pointer [&_select]:appearance-none [&_select]:bg-transparent [&_select]:px-1 [&_select]:text-muted-foreground [&_select]:outline-none",
        "[&_input]:text-base [&_select]:text-base md:[&_input]:text-sm md:[&_select]:text-sm",
        className,
      )}>
      {children}
    </div>
  );
}

/** Where the row stands: saving, 已存 (fading), 未存, or the new row's create button. */
export function RowState<T extends Values>({ row, name, createLabel = "新增" }: {
  row: GridRow<T>; name: string; createLabel?: string;
}) {
  if (row.status === "saving") {
    return <span role="status" className="text-muted-foreground inline-flex items-center gap-1 text-xs"><Spinner className="size-3" />儲存中</span>;
  }
  if (row.creating) {
    return row.dirty ? (
      <button type="button" onClick={row.submit} aria-label={`${createLabel} ${name}`}
        className="bg-accent text-accent-foreground hover:bg-accent/80 inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs">
        <PlusIcon className="size-3" />{createLabel}
      </button>
    ) : null;
  }
  if (row.status === "error") return <span className="text-destructive text-xs">未存</span>;
  if (row.status === "saved" && !row.dirty) {
    return <span className="text-success-foreground inline-flex animate-[fade_2.4s_ease-in_forwards] items-center gap-1 text-xs"><CheckIcon className="size-3" />已存</span>;
  }
  return null;
}

/** Why the row did not save, each field named, under the row. */
export function RowError<T extends Values>({ row, labels, colSpan }: {
  row: GridRow<T>; labels: Record<string, string>; colSpan: number;
}) {
  if (row.status !== "error") return null;
  const details = Object.entries(row.fields).map(([name, messages]) => `${labels[name] ? `${labels[name]}：` : ""}${messages.join(" ")}`);
  return (
    <tr>
      <td colSpan={colSpan} className="px-1 pb-2">
        <div role="alert" className="bg-destructive/10 text-destructive rounded-md px-3 py-2 text-xs leading-relaxed">
          {row.error} {details.join("；")}
          <span className="block opacity-80">{row.creating ? "改好後按 Enter 再試，Esc 清掉那一格。" : "改好後離開格子會再存，Esc 還原那一格。"}</span>
        </div>
      </td>
    </tr>
  );
}

/** Rows tell their page which edits would be lost, so switching the day or collapsing asks first. */
export function useRiskRegistry() {
  const risky = useRef(new Set<string>());
  const report = useRef((key: string, atRisk: boolean) => {
    if (atRisk) risky.current.add(key);
    else risky.current.delete(key);
  }).current;
  const confirmLeave = (prefix = "") =>
    ![...risky.current].some((key) => key.startsWith(prefix))
    || window.confirm("還有沒存成功的修改或還沒新增的列，放棄嗎？");
  return { report, confirmLeave };
}

// Layout effects, so the registry changes in the same commit that shows 未存: a click landing
// before passive effects run would otherwise skip the confirm.
export function useReportRisk(report: (key: string, atRisk: boolean) => void, key: string, atRisk: boolean) {
  useLayoutEffect(() => { report(key, atRisk); }, [report, key, atRisk]);
  useLayoutEffect(() => () => report(key, false), [report, key]);
}

/** The browser asks before closing or reloading the page while something is unsaved. */
function useDraftWarning(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
}

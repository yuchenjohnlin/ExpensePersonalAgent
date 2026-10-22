/** The only code that calls the server's ledger (/api/categories, /api/expenses, /api/lines, /api/calendar).
 *
 * Reads are TanStack Query queries, cached under the keys below. Every write answers the whole
 * expense; the hooks put that answer in the cache and mark what else may now be out of date
 * (the month totals, the day, the unreviewed list, receipt cards that show the expense), so any
 * page showing them refreshes by itself. */
import { useMutation, useQueries, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { api } from "@/shared/api/client";

import type { Category, Day, ExpenseChanges, ExpenseDetail, Month, MonthDay } from "./types";

export const ledgerKeys = {
  categories: ["categories"] as const,
  month: (month: string) => ["calendar", month] as const,
  day: (day: string) => ["day", day] as const,
  expense: (id: number) => ["expense", id] as const,
  unreviewed: ["expenses", "unreviewed"] as const,
};

export function useCategories() {
  return useQuery({ queryKey: ledgerKeys.categories, queryFn: () => api.get<Category[]>("/api/categories"), staleTime: Infinity });
}

/** Every month the day picker shows (a week can reach into two): each day's total and merchants. */
export function useMonths(months: string[]) {
  const results = useQueries({
    queries: months.map((month) => ({
      queryKey: ledgerKeys.month(month),
      queryFn: () => api.get<Month>(`/api/calendar?month=${month}`),
    })),
  });
  const days = new Map<string, MonthDay>();
  for (const result of results) for (const day of result.data?.days ?? []) days.set(day.date, day);
  return {
    days,
    totals: Object.fromEntries(months.map((month, index) => [month, results[index]?.data?.total])) as Record<string, string | undefined>,
    known: results.every((result) => result.data),
    loading: results.some((result) => result.isFetching),
    error: results.find((result) => result.error)?.error ?? null,
  };
}

export function useDay(day: string) {
  return useQuery({ queryKey: ledgerKeys.day(day), queryFn: () => api.get<Day>(`/api/calendar/day?date=${day}`) });
}

export function useUnreviewed() {
  return useQuery({ queryKey: ledgerKeys.unreviewed, queryFn: () => api.get<ExpenseDetail[]>("/api/expenses/unreviewed") });
}

/** After a write: the expense as answered, and everything that may show it marked stale. */
export function expenseChanged(client: QueryClient, expense?: ExpenseDetail) {
  if (expense) {
    // Shown at once wherever it already is; the refetches below then bring totals and moves.
    const replace = (list: ExpenseDetail[]) => list.map((old) => (old.id === expense.id ? expense : old));
    client.setQueryData(ledgerKeys.expense(expense.id), expense);
    client.setQueriesData<Day>({ queryKey: ["day"] }, (day) => day && { ...day, expenses: replace(day.expenses) });
    client.setQueryData<ExpenseDetail[]>(ledgerKeys.unreviewed, (list) => list && replace(list));
  }
  for (const key of [["calendar"], ["day"], ledgerKeys.unreviewed, ["receipts"]]) {
    client.invalidateQueries({ queryKey: key });
  }
}

function useExpenseWrite<Variables>(write: (variables: Variables) => Promise<ExpenseDetail>) {
  const client = useQueryClient();
  return useMutation({ mutationFn: write, onSuccess: (expense) => expenseChanged(client, expense) });
}

export function useUpdateExpense() {
  return useExpenseWrite(({ id, changes }: { id: number; changes: ExpenseChanges }) =>
    api.patch<ExpenseDetail>(`/api/expenses/${id}`, changes));
}

export function useDeleteExpense() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.delete<{ deleted: number }>(`/api/expenses/${id}`),
    onSuccess: ({ deleted }) => {
      client.removeQueries({ queryKey: ledgerKeys.expense(deleted) });
      expenseChanged(client);
    },
  });
}

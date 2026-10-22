/** The only code that calls the server's receipts module (/api/receipts...).
 *
 * While any receipt is being read, the queries that show it ask again every few seconds, so a
 * card turns from 讀取中 into 已入帳 or 要看一下 by itself. Writes that change the ledger tell
 * the ledger's queries too (expenseChanged). */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { expenseChanged } from "@/features/ledger";
import { api } from "@/shared/api/client";

import type { ReceiptCard, ReceiptPage, ReceiptState } from "./types";

const POLL_MS = 3000;

export const receiptKeys = {
  all: ["receipts"] as const,
  list: (state: ReceiptState | null, page: number) => ["receipts", "list", state, page] as const,
  one: (id: number) => ["receipts", "one", id] as const,
  forExpenses: (ids: number[]) => ["receipts", "for-expenses", ids] as const,
};

export function useReceipts(state: ReceiptState | null, page = 1) {
  return useQuery({
    queryKey: receiptKeys.list(state, page),
    queryFn: () => api.get<ReceiptPage>(`/api/receipts?page=${page}${state ? `&state=${state}` : ""}`),
    placeholderData: keepPreviousData,
    refetchInterval: (query) => (query.state.data?.counts.reading ? POLL_MS : false),
  });
}

export function useReceipt(id: number | null) {
  return useQuery({
    queryKey: receiptKeys.one(id ?? 0),
    queryFn: () => api.get<ReceiptCard>(`/api/receipts/${id}`),
    enabled: id !== null,
    refetchInterval: (query) => (query.state.data?.state === "reading" ? POLL_MS : false),
  });
}

/** The receipt each expense came from (expense id -> card), for showing its photo beside it. */
export function useReceiptsForExpenses(expenseIds: number[]) {
  const ids = [...expenseIds].sort((a, b) => a - b);
  return useQuery({
    queryKey: receiptKeys.forExpenses(ids),
    queryFn: () => api.get<{ receipts: Record<string, ReceiptCard> }>(
      `/api/receipts/for-expenses?${ids.map((id) => `expense_id=${id}`).join("&")}`),
    enabled: ids.length > 0,
    select: (data) => data.receipts,
  });
}

export type UploadInput = { files: File[]; groups: number[][]; allowDuplicates?: boolean };

export function useUpload() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ files, groups, allowDuplicates }: UploadInput) => {
      const form = new FormData();
      for (const file of files) form.append("photos", file, file.name);
      form.append("groups", JSON.stringify(groups));
      if (allowDuplicates) form.append("allow_duplicates", "true");
      return api.post<{ receipts: ReceiptCard[] }>("/api/receipts", form);
    },
    onSuccess: () => client.invalidateQueries({ queryKey: receiptKeys.all }),
  });
}

function useReceiptWrite<Variables>(write: (variables: Variables) => Promise<ReceiptCard>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: write,
    onSuccess: (card) => {
      client.setQueryData(receiptKeys.one(card.id), card);
      expenseChanged(client); // also marks every receipt query stale
    },
  });
}

export function useReadAgain() {
  return useReceiptWrite((id: number) => api.post<ReceiptCard>(`/api/receipts/${id}/readings`));
}

export type PostingInput = {
  title: string; amount: string; date: string; category_id: number; merchant: string; notes?: string;
  tax: string | null; tip: string | null; receipt_discount: string | null; lines: boolean;
};

export function usePostByHand() {
  return useReceiptWrite(({ id, input }: { id: number; input: PostingInput }) =>
    api.post<ReceiptCard>(`/api/receipts/${id}/posting`, input));
}

export function useUnpost() {
  return useReceiptWrite((id: number) => api.delete<ReceiptCard>(`/api/receipts/${id}/posting`));
}

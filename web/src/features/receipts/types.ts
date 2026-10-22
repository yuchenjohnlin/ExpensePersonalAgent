// The shapes the server's receipts module answers (server/README.md, "Receipts").

export type ReceiptState = "reading" | "needs_review" | "posted";

export type ReceiptPhoto = {
  id: number;
  position: number;
  original_name: string;
  preview_url: string;
  thumbnail_url: string;
  original_url: string;
};

export type ReadingSummary = {
  id: number;
  status: "queued" | "running" | "succeeded" | "failed";
  provider: string;
  model: string;
  merchant: string | null;
  date: string | null;
  amount: string | null;
  tax: string | null;
  item_count: number;
  checks: string[]; // the server's arithmetic checks that failed
  warnings: string[]; // what the model itself noticed
  error_code: string;
  error_message: string;
  elapsed_ms: number | null;
  completed_at: string | null;
};

export type PostedExpense = {
  id: number;
  title: string;
  merchant: string;
  date: string;
  amount: string;
  category: string;
  reviewed_at: string | null;
  line_count: number;
};

export type ReceiptCard = {
  id: number;
  created_at: string;
  state: ReceiptState;
  reasons: string[]; // why it needs a look
  photos: ReceiptPhoto[];
  reading: ReadingSummary | null;
  posting: null | {
    mode: "auto" | "manual";
    reading_id: number | null;
    skipped: { index: number; description: string; amount: string | null; reason: string }[];
    expense: PostedExpense | null;
  };
};

export type ReceiptPage = {
  receipts: ReceiptCard[];
  page: number;
  pages: number;
  total: number;
  counts: { reading: number; needs_review: number };
};

export type Duplicate = { index: number; existing_photo_ids: number[]; same_as_indices: number[] };

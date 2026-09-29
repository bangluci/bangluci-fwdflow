export type HsSuggestItem = {
  code: string;
  description_vi: string;
  description_en: string | null;
  rank: number;
  rrf_score: number;
  cosine: number | null;
  explanation: string | null;
  needs_review: boolean;
};

export type HsSuggestResult = {
  log_id: number;
  status: "OK" | "INSUFFICIENT" | "SEARCH_ONLY";
  degraded: boolean;
  hint: string | null;
  items: HsSuggestItem[];
};

/** `84713020` → `8471.30.20` (dạng hiển thị của Danh mục; API luôn dùng 8 chữ số liền). */
export const formatHsCode = (code: string): string => (code.length === 8 ? `${code.slice(0, 4)}.${code.slice(4, 6)}.${code.slice(6)}` : code);

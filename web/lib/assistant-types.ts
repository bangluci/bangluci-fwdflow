export type ChartSpec = { type: "bar" | "line" | "pie"; x: string; y: string };

export type AssistantAnswer = {
  log_id: number;
  sql: string | null;
  columns: string[];
  rows: (string | number | boolean | null)[][];
  truncated: boolean;
  answer: string | null;
  answer_checked: boolean | null;
  chart: ChartSpec | null;
  message: string | null;
};

/** Câu hỏi mẫu để bấm thử; đều trả lời được bằng view của mọi vai trò nội bộ. */
export const EXAMPLE_QUESTIONS = [
  "Có bao nhiêu lô đang ở từng trạng thái?",
  "Những container nào đã quá hạn free time?",
  "Tài xế nào giao nhiều kiện nhất trong 30 ngày qua?",
  "Khách nào có nhiều lô nhất năm nay?",
];

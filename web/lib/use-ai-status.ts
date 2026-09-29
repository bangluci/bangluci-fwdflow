import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./api";

export type AiStatus = {
  enabled: boolean;
  reason: string | null;
  provider: "anthropic" | "gemini";
  /** Tên dịch vụ nhận dữ liệu, ví dụ "Gemini API (Google, Mỹ)"; dùng trong cảnh báo gửi dữ liệu ra ngoài. */
  provider_label: string;
};

export const FALLBACK_PROVIDER_LABEL = "dịch vụ AI bên ngoài (Mỹ)";

export const useAiStatus = () => useQuery({ queryKey: ["ai-status"], queryFn: () => apiFetch<AiStatus>("/api/ai/status"), staleTime: 60_000 });

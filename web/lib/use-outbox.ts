"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { flushOutbox, listItems, removeItem, requestPersistence, type OutboxItem } from "./driver-outbox";

/** Hàng chờ gửi của tài xế: tự gửi lại khi mở app, khi có mạng, khi quay lại màn hình; có nút gửi tay. */
export function useOutbox() {
  const queryClient = useQueryClient();
  const [items, setItems] = useState<OutboxItem[]>([]);
  const [sending, setSending] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setItems(await listItems());
    } catch {
      setItems([]);
    }
  }, []);

  const flush = useCallback(async () => {
    setSending(true);
    try {
      const sent = await flushOutbox();
      if (sent > 0) await queryClient.invalidateQueries({ queryKey: ["driver-tasks"] });
    } finally {
      setSending(false);
      await refresh();
    }
  }, [queryClient, refresh]);

  useEffect(() => {
    void requestPersistence();
    const first = setTimeout(() => void flush(), 0);
    const onVisible = () => document.visibilityState === "visible" && void flush();
    window.addEventListener("online", flush);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearTimeout(first);
      window.removeEventListener("online", flush);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [flush]);

  const discard = useCallback(async (id: string) => {
    await removeItem(id);
    await refresh();
  }, [refresh]);

  return { items, sending, flush, refresh, discard };
}

"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

/** Bộ lọc nằm trên URL (chia sẻ được, tải lại vẫn giữ). Giá trị rỗng hoặc bằng mặc định thì bỏ khỏi URL. */
export function useUrlFilters<T extends Record<string, string>>(defaults: T) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const value = useMemo(
    () => Object.fromEntries(Object.keys(defaults).map((key) => [key, params.get(key) ?? defaults[key]])) as T,
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `defaults` là hằng của từng màn
    [params],
  );
  const set = useCallback(
    (patch: Partial<T>) => {
      const next = new URLSearchParams(params.toString());
      for (const [key, raw] of Object.entries(patch)) {
        if (raw === "" || raw === defaults[key]) next.delete(key);
        else next.set(key, String(raw));
      }
      if (!("page" in patch) && "page" in defaults) next.delete("page");
      const query = next.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [params, pathname, router],
  );
  return [value, set] as const;
}

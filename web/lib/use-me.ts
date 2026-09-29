import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./api";
import type { Role } from "./roles";

export type Me = {
  id: number;
  email: string | null;
  phone: string | null;
  full_name: string;
  role: Role;
  customer_id: number | null;
  driver_id: number | null;
  is_active: boolean;
  permissions: string[];
};

export const meQuery = { queryKey: ["me"], queryFn: () => apiFetch<Me>("/api/auth/me") } as const;

export const useMe = () => useQuery({ ...meQuery, staleTime: 60_000 });

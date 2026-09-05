import { createContext, useContext, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import type { Merchant } from "../types/api";

interface MerchantContextValue {
  merchant: Merchant | null;
  isLoading: boolean;
  isError: boolean;
}

const MerchantContext = createContext<MerchantContextValue>({ merchant: null, isLoading: true, isError: false });

export function MerchantProvider({ children }: { children: ReactNode }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["merchants"],
    queryFn: () => apiFetch<{ items: Merchant[] }>("/api/v1/merchants"),
  });

  // Pre-auth convenience: use the first active merchant (TechNest in demo
  // mode). Once login lands, this becomes "the merchant(s) this user
  // belongs to" via /api/v1/me.
  const merchant = data?.items?.[0] ?? null;

  return <MerchantContext.Provider value={{ merchant, isLoading, isError }}>{children}</MerchantContext.Provider>;
}

export function useMerchant() {
  return useContext(MerchantContext);
}

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import type { DashboardSummary, RevenueTrendPoint, TopProduct } from "../types/api";

export function useDashboardSummary(merchantId: string | undefined) {
  return useQuery({
    queryKey: ["dashboard-summary", merchantId],
    queryFn: () => apiFetch<DashboardSummary>(`/api/v1/dashboard/summary?merchant_id=${merchantId}`),
    enabled: Boolean(merchantId),
  });
}

export function useRevenueTrend(merchantId: string | undefined, freq: "D" | "W" | "M" = "W") {
  return useQuery({
    queryKey: ["revenue-trend", merchantId, freq],
    queryFn: () => apiFetch<{ points: RevenueTrendPoint[] }>(`/api/v1/dashboard/revenue-trend?merchant_id=${merchantId}&freq=${freq}`),
    enabled: Boolean(merchantId),
  });
}

export function useTopProducts(merchantId: string | undefined, limit = 5) {
  return useQuery({
    queryKey: ["top-products", merchantId, limit],
    queryFn: () => apiFetch<{ products: TopProduct[] }>(`/api/v1/dashboard/top-products?merchant_id=${merchantId}&limit=${limit}`),
    enabled: Boolean(merchantId),
  });
}

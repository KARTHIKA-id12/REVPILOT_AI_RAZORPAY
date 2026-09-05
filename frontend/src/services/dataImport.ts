import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiUpload } from "../lib/api";

interface SkippedRow {
  row: number;
  reason: string;
}

export interface UploadSchema {
  customers_csv: { required_or_optional_columns: string[] };
  orders_csv: { required_or_optional_columns: string[] };
}

export interface CustomersUploadResult {
  customers_created: number;
  customers_matched_existing: number;
  rows_skipped: SkippedRow[];
}

export interface OrdersUploadResult {
  orders_created: number;
  rows_skipped: SkippedRow[];
  analytics_refreshed: {
    opportunities_detected: number;
    opportunities_by_type: Record<string, number>;
  };
}

export function useUploadSchema() {
  return useQuery({
    queryKey: ["data-upload-schema"],
    queryFn: () => apiFetch<UploadSchema>("/api/v1/data/schema"),
  });
}

export function useUploadCustomers(merchantId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => apiUpload<CustomersUploadResult>(`/api/v1/data/upload/customers?merchant_id=${merchantId}`, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary", merchantId] });
    },
  });
}

export function useUploadOrders(merchantId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => apiUpload<OrdersUploadResult>(`/api/v1/data/upload/orders?merchant_id=${merchantId}`, file),
    onSuccess: () => {
      // Orders import triggers a real analytics recompute server-side —
      // invalidate every view whose numbers could now be stale.
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary", merchantId] });
      queryClient.invalidateQueries({ queryKey: ["opportunities", merchantId] });
      queryClient.invalidateQueries({ queryKey: ["revenue-trend", merchantId] });
    },
  });
}

export function useResetDefaultData(merchantId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<{ status: string; message: string }>(`/api/v1/data/reset-default?merchant_id=${merchantId}`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries();
    },
  });
}

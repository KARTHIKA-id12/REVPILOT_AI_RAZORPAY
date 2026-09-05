import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";

export type CustomerRow = {
  id: string; name: string; email: string | null; order_count: number;
  total_spend: number; last_order_at: string | null;
};
export type ProductRow = {
  id: string; sku: string; name: string; price_amount: number; currency: string;
  stock_qty: number; stock_status: string; image_url: string | null;
};

export function useCustomers(merchantId: string | undefined, q: string) {
  return useQuery({
    queryKey: ["merchant-customers", merchantId, q],
    queryFn: () => apiFetch<{ items: CustomerRow[]; total: number }>(
      `/api/v1/merchant/customers?merchant_id=${merchantId}&q=${encodeURIComponent(q)}`,
    ),
    enabled: Boolean(merchantId),
  });
}

export function useProducts(merchantId: string | undefined, q: string) {
  return useQuery({
    queryKey: ["merchant-products", merchantId, q],
    queryFn: () => apiFetch<{ items: ProductRow[]; total: number }>(
      `/api/v1/merchant/products?merchant_id=${merchantId}&q=${encodeURIComponent(q)}`,
    ),
    enabled: Boolean(merchantId),
  });
}
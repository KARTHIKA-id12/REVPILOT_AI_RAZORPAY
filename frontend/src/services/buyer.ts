import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import type { BuyerQueryResponse, CartState, CheckoutPreview, CheckoutResult } from "../types/api";

export function useBuyerQuery() {
  return useMutation({
    mutationFn: ({ merchantId, query, maxBudget }: { merchantId: string; query: string; maxBudget?: number }) =>
      apiFetch<BuyerQueryResponse>("/api/v1/agent/buyer/query", {
        method: "POST",
        body: JSON.stringify({ merchant_id: merchantId, query, max_budget: maxBudget }),
      }),
  });
}

export function useBuyerCart(merchantId: string | undefined, sessionRef: string) {
  return useQuery({
    queryKey: ["buyer-cart", merchantId, sessionRef],
    queryFn: () => apiFetch<CartState>(`/api/v1/agent/cart?merchant_id=${merchantId}&session_ref=${encodeURIComponent(sessionRef)}`),
    enabled: Boolean(merchantId),
  });
}

export function useBuyerCartAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      merchantId: string;
      sessionRef: string;
      action: "add" | "set" | "remove" | "clear";
      productId?: string;
      quantity?: number;
      maxTotal?: number;
    }) =>
      apiFetch<CartState>("/api/v1/agent/cart", {
        method: "POST",
        body: JSON.stringify({
          merchant_id: input.merchantId,
          session_ref: input.sessionRef,
          action: input.action,
          product_id: input.productId,
          quantity: input.quantity,
          max_total: input.maxTotal,
        }),
      }),
    onSuccess: (_, input) => {
      queryClient.invalidateQueries({ queryKey: ["buyer-cart", input.merchantId, input.sessionRef] });
    },
  });
}

export function useCheckoutPreview() {
  return useMutation({
    mutationFn: ({ merchantId, sessionRef }: { merchantId: string; sessionRef: string }) =>
      apiFetch<CheckoutPreview>("/api/v1/agent/checkout/preview", {
        method: "POST",
        body: JSON.stringify({ merchant_id: merchantId, session_ref: sessionRef }),
      }),
  });
}

export function useCheckoutConfirm() {
  return useMutation({
    mutationFn: (input: {
      merchantId: string;
      sessionRef: string;
      previewId: string;
      buyerName: string;
      buyerEmail: string;
    }) =>
      apiFetch<CheckoutResult>("/api/v1/agent/checkout/confirm", {
        method: "POST",
        body: JSON.stringify({
          merchant_id: input.merchantId,
          session_ref: input.sessionRef,
          preview_id: input.previewId,
          confirmed: true,
          buyer_name: input.buyerName,
          buyer_email: input.buyerEmail,
          idempotency_key: `checkout_${input.sessionRef}`,
        }),
      }),
  });
}

export function useCheckoutVerify() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ merchantId, orderId }: { merchantId: string; orderId: string }) =>
      apiFetch<CheckoutResult>("/api/v1/agent/checkout/verify", {
        method: "POST",
        body: JSON.stringify({ merchant_id: merchantId, order_id: orderId, demo: true }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["buyer-cart"] });
    },
  });
}
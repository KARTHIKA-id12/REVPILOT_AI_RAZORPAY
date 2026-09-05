import { useMutation } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import type { SimulationCompareResponse } from "../types/api";

interface CompareParams {
  merchantId: string;
  opportunityId?: string;
  productIds?: string[];
  discountPercents: number[];
}

export function useCompareSimulation() {
  return useMutation({
    mutationFn: ({ merchantId, opportunityId, productIds, discountPercents }: CompareParams) =>
      apiFetch<SimulationCompareResponse>(`/api/v1/simulations/compare?merchant_id=${merchantId}`, {
        method: "POST",
        body: JSON.stringify({
          opportunity_id: opportunityId ?? null,
          product_ids: productIds ?? null,
          discount_percents: discountPercents,
        }),
      }),
  });
}

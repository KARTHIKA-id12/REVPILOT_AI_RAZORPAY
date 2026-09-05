import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import type { Opportunity, OpportunityListResponse } from "../types/api";

export function useOpportunities(merchantId: string | undefined, opts?: { type?: string; page?: number; pageSize?: number }) {
  const page = opts?.page ?? 1;
  const pageSize = opts?.pageSize ?? 20;
  const typeParam = opts?.type ? `&type=${opts.type}` : "";

  return useQuery({
    queryKey: ["opportunities", merchantId, opts?.type, page, pageSize],
    queryFn: () =>
      apiFetch<OpportunityListResponse>(
        `/api/v1/opportunities?merchant_id=${merchantId}&page=${page}&page_size=${pageSize}${typeParam}`,
      ),
    enabled: Boolean(merchantId),
  });
}

export function useOpportunity(opportunityId: string | undefined) {
  return useQuery({
    queryKey: ["opportunity", opportunityId],
    queryFn: () => apiFetch<Opportunity>(`/api/v1/opportunities/${opportunityId}`),
    enabled: Boolean(opportunityId),
  });
}

export function useRefreshOpportunities(merchantId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch(`/api/v1/opportunities/refresh?merchant_id=${merchantId}`, { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["opportunities"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
    },
  });
}

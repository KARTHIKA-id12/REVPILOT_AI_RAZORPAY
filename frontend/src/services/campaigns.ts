import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import type { CampaignDetail, CampaignSummary } from "../types/api";

export function useCampaigns(merchantId: string | undefined, status?: string) {
  const statusParam = status ? `&status=${status}` : "";
  return useQuery({
    queryKey: ["campaigns", merchantId, status],
    queryFn: () => apiFetch<{ items: CampaignSummary[]; total: number }>(`/api/v1/campaigns?merchant_id=${merchantId}${statusParam}`),
    enabled: Boolean(merchantId),
  });
}

export function useCampaign(campaignId: string | undefined) {
  return useQuery({
    queryKey: ["campaign", campaignId],
    queryFn: () => apiFetch<CampaignDetail>(`/api/v1/campaigns/${campaignId}`),
    enabled: Boolean(campaignId),
  });
}

export function useCampaignAction(campaignId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (action: "pause" | "cancel") => apiFetch(`/api/v1/campaigns/${campaignId}/${action}`, { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["campaign", campaignId] });
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
    },
  });
}

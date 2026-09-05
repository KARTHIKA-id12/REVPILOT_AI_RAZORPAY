import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import type { ApprovalRequestItem } from "../types/api";

export function useApprovals(merchantId: string | undefined, status: string = "pending") {
  return useQuery({
    queryKey: ["approvals", merchantId, status],
    queryFn: () => apiFetch<{ items: ApprovalRequestItem[] }>(`/api/v1/approvals?merchant_id=${merchantId}&status=${status}`),
    enabled: Boolean(merchantId),
  });
}

export function useDecideApproval(merchantId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ approvalId, decision }: { approvalId: string; decision: "approve" | "reject" }) =>
      apiFetch(`/api/v1/approvals/${approvalId}/${decision}?merchant_id=${merchantId}`, { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
      queryClient.invalidateQueries({ queryKey: ["opportunities"] });
    },
  });
}

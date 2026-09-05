import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import type { AgentMessageResponse, AgentSessionSummary } from "../types/api";

export function useCreateAgentSession() {
  return useMutation({
    mutationFn: (merchantId: string) =>
      apiFetch<AgentSessionSummary>("/api/v1/agent/sessions", {
        method: "POST",
        body: JSON.stringify({ merchant_id: merchantId, channel: "merchant_console" }),
      }),
  });
}

export function useSendAgentMessage(sessionId: string | undefined, merchantId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (content: string) =>
      apiFetch<AgentMessageResponse>(`/api/v1/agent/sessions/${sessionId}/messages?merchant_id=${merchantId}`, {
        method: "POST",
        body: JSON.stringify({ content }),
      }),
    onSuccess: () => {
      // A message may have created a pending approval — keep the
      // Approval Center and dashboard in sync.
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
    },
  });
}

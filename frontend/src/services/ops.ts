import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";

export interface AuditEntry {
  id: string;
  action: string;
  tool: string | null;
  input_summary: string | null;
  reason: string | null;
  policy_result: string | null;
  permission_result: string | null;
  approval_id: string | null;
  external_id: string | null;
  result: string;
  error: string | null;
  recovery_action: string | null;
  request_id: string | null;
  agent_session_id: string | null;
  created_at: string | null;
}

export interface OpsNotification {
  id: string;
  type: string;
  title: string;
  body: string;
  read_at: string | null;
  created_at: string | null;
}

export interface ActionCenter {
  counts: {
    pending_approvals: number;
    unread_notifications: number;
    failed_actions_24h: number;
    blocked_actions_24h: number;
  };
  recent_failures: AuditEntry[];
  pending_approvals: Array<{
    id: string;
    action_code: string;
    risk_level: string;
    campaign_id: string | null;
    created_at: string | null;
  }>;
  notifications: OpsNotification[];
}

export interface TraceSummary {
  id: string;
  channel: string;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  message_count: number;
  tool_call_count: number;
  action_count: number;
  last_activity_at: string | null;
}

export function useAuditLedger(merchantId: string | undefined, result: string, search: string) {
  const params = new URLSearchParams({ merchant_id: merchantId ?? "", limit: "50" });
  if (result) params.set("result", result);
  if (search.trim()) params.set("search", search.trim());
  return useQuery({
    queryKey: ["ops-audit", merchantId, result, search],
    queryFn: () => apiFetch<{ items: AuditEntry[]; total: number }>(`/api/v1/ops/audit?${params}`),
    enabled: Boolean(merchantId),
  });
}

export function useActionCenter(merchantId: string | undefined) {
  return useQuery({
    queryKey: ["ops-action-center", merchantId],
    queryFn: () => apiFetch<ActionCenter>(`/api/v1/ops/action-center?merchant_id=${merchantId}`),
    enabled: Boolean(merchantId),
  });
}

export function useAgentTraces(merchantId: string | undefined) {
  return useQuery({
    queryKey: ["ops-traces", merchantId],
    queryFn: () => apiFetch<{ items: TraceSummary[]; total: number }>(`/api/v1/ops/traces?merchant_id=${merchantId}`),
    enabled: Boolean(merchantId),
  });
}

export function useMarkAllNotificationsRead(merchantId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<{ marked_read: number }>(
      `/api/v1/ops/notifications/read-all?merchant_id=${merchantId}`,
      { method: "POST" },
    ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ops-action-center", merchantId] }),
  });
}
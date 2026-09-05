import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import type { PermissionItem, PermissionMode, PolicyItem } from "../types/api";

export function usePermissions(merchantId: string | undefined) {
  return useQuery({
    queryKey: ["settings-permissions", merchantId],
    queryFn: () => apiFetch<{ items: PermissionItem[] }>(`/api/v1/settings/permissions?merchant_id=${merchantId}`),
    enabled: Boolean(merchantId),
  });
}

export function useUpdatePermission(merchantId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ actionCode, mode }: { actionCode: string; mode: PermissionMode }) =>
      apiFetch(`/api/v1/settings/permissions?merchant_id=${merchantId}`, {
        method: "PUT",
        body: JSON.stringify({ permissions: [{ action_code: actionCode, mode }] }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings-permissions", merchantId] }),
  });
}

export function usePolicies(merchantId: string | undefined) {
  return useQuery({
    queryKey: ["settings-policies", merchantId],
    queryFn: () => apiFetch<{ items: PolicyItem[] }>(`/api/v1/settings/policies?merchant_id=${merchantId}`),
    enabled: Boolean(merchantId),
  });
}

export function useUpdatePolicy(merchantId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ code, value }: { code: string; value: number | boolean }) =>
      apiFetch(`/api/v1/settings/policies?merchant_id=${merchantId}`, {
        method: "PUT",
        body: JSON.stringify({ policies: [{ code, value }] }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings-policies", merchantId] }),
  });
}

export function useEmergencyStop(merchantId: string | undefined) {
  return useQuery({
    queryKey: ["emergency-stop", merchantId],
    queryFn: () => apiFetch<{ enabled: boolean }>(`/api/v1/settings/emergency-stop?merchant_id=${merchantId}`),
    enabled: Boolean(merchantId),
  });
}

export function useSetEmergencyStop(merchantId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) =>
      apiFetch(`/api/v1/settings/emergency-stop?merchant_id=${merchantId}`, {
        method: "POST",
        body: JSON.stringify({ enabled }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["emergency-stop", merchantId] }),
  });
}

import { useMutation, useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import type { FailureLabResult, FailureLabScenario } from "../types/api";

export function useFailureScenarios() {
  return useQuery({
    queryKey: ["failure-scenarios"],
    queryFn: () => apiFetch<{ scenarios: FailureLabScenario[] }>("/api/v1/demo/failures/scenarios"),
  });
}

export function useTriggerFailure(merchantId: string | undefined) {
  return useMutation({
    mutationFn: (scenario: string) =>
      apiFetch<FailureLabResult>(`/api/v1/demo/failures/${scenario}?merchant_id=${merchantId}`, { method: "POST" }),
  });
}

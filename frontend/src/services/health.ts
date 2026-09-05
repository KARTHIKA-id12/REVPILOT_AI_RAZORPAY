import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";

export interface HealthStatus {
  status: "healthy" | "degraded";
  database: "healthy" | "unhealthy";
  ai: "configured" | "demo_mode";
  payment_provider: "razorpay_test" | "mock";
  version: string;
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => apiFetch<HealthStatus>("/health"),
    refetchInterval: 30_000,
  });
}

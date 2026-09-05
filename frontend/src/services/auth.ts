import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";

const TOKEN_KEY = "revpilot_access_token";

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  merchants: { merchant_id: string; role_id: string }[];
}

interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function clearStoredToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (credentials: { email: string; password: string }) =>
      apiFetch<LoginResponse>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify(credentials),
      }),
    onSuccess: (data) => {
      localStorage.setItem(TOKEN_KEY, data.access_token);
      // A different user may now be signed in — every merchant-scoped
      // query in the app must refetch rather than keep showing whatever
      // the previous (possibly anonymous demo-mode) session saw.
      queryClient.invalidateQueries();
    },
  });
}

export function useCurrentUser() {
  return useQuery({
    queryKey: ["auth-me"],
    queryFn: () => apiFetch<AuthUser>("/api/v1/auth/me"),
    enabled: Boolean(getStoredToken()),
    retry: false,
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return () => {
    clearStoredToken();
    queryClient.invalidateQueries();
  };
}

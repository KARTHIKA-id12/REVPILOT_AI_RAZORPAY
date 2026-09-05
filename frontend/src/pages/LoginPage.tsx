import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useLogin } from "../services/auth";
import { ErrorState } from "../components/EmptyState";

export function LoginPage() {
  const navigate = useNavigate();
  const login = useLogin();
  const [email, setEmail] = useState("owner@technest.demo");
  const [password, setPassword] = useState("RevPilotDemo123!");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    login.mutate(
      { email, password },
      { onSuccess: () => navigate("/") },
    );
  }

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-sm flex-col justify-center">
      <div className="mb-6 text-center">
        <h1 className="text-lg font-semibold tracking-tight text-[var(--color-text-primary)]">Sign in to RevPilot AI</h1>
        <p className="mt-1.5 text-xs text-[var(--color-text-secondary)]">
          Use the seeded TechNest owner account, or your own credentials.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <div>
          <label htmlFor="email" className="mb-1 block text-xs font-medium text-[var(--color-text-secondary)]">
            Email
          </label>
          <input
            id="email"
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
          />
        </div>

        <div>
          <label htmlFor="password" className="mb-1 block text-xs font-medium text-[var(--color-text-secondary)]">
            Password
          </label>
          <input
            id="password"
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
          />
        </div>

        {login.isError && (
          <ErrorState message={login.error instanceof Error ? login.error.message : "Sign in failed. Check your credentials."} />
        )}

        <button
          type="submit"
          disabled={login.isPending}
          className="w-full rounded-md bg-[var(--color-accent)] px-3 py-2 text-sm font-medium text-[var(--color-bg)] transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {login.isPending ? "Signing in…" : "Sign in"}
        </button>

        <p className="text-center text-[11px] text-[var(--color-text-secondary)]">
          Demo mode is also browsable without signing in — this account scopes the
          Agent, Approvals, and Settings actions to your own role.
        </p>
      </form>
    </div>
  );
}

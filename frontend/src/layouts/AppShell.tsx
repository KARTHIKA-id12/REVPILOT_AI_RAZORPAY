import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { SystemStatusBadge } from "../components/SystemStatusBadge";
import { useMerchant } from "../app/MerchantContext";
import { useCurrentUser, useLogout, getStoredToken } from "../services/auth";

const NAV_ITEMS = [
  { label: "Dashboard", to: "/" },
  { label: "Mission Workflow", to: "/mission" },
  { label: "Notifications", to: "/notifications" },
  { label: "Opportunities", to: "/opportunities" },
  { label: "Campaigns", to: "/campaigns" },
  { label: "Shop with AI", to: "/shop" },
  { label: "Agent", to: "/agent" },
  { label: "Approvals", to: "/approvals" },
  { label: "Audit", to: "/audit" },
  { label: "Control Room", to: "/control-room" },
  { label: "Failure Lab", to: "/failure-lab" },
  { label: "Upload Data", to: "/data-upload" },
  { label: "Settings", to: "/settings" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { merchant } = useMerchant();
  const hasToken = Boolean(getStoredToken());
  const { data: user } = useCurrentUser();
  const logout = useLogout();

  return (
    <div className="min-h-screen bg-[var(--color-bg)] text-[var(--color-text-primary)]">
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] px-4 py-3 sm:px-6 sm:py-4">
        <div className="flex items-center gap-3">
          <span className="text-lg font-semibold tracking-tight">RevPilot AI</span>
          <span className="rounded-full border border-[var(--color-border)] px-2 py-0.5 text-[10px] uppercase tracking-wide text-[var(--color-text-secondary)]">
            Demo
          </span>
          {merchant && <span className="text-sm text-[var(--color-text-secondary)]">{merchant.name}</span>}
        </div>
        <div className="flex items-center gap-3">
          {hasToken && user ? (
            <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
              <span>{user.email}</span>
              <button
                type="button"
                onClick={logout}
                className="rounded-md border border-[var(--color-border)] px-2 py-1 text-[var(--color-text-primary)] hover:bg-[var(--color-surface)]"
              >
                Sign out
              </button>
            </div>
          ) : (
            <NavLink
              to="/login"
              className="rounded-md border border-[var(--color-border)] px-2 py-1 text-xs text-[var(--color-text-primary)] hover:bg-[var(--color-surface)]"
            >
              Sign in
            </NavLink>
          )}
          <SystemStatusBadge />
        </div>
      </header>

      <div className="flex flex-col md:flex-row">
        <nav aria-label="Primary navigation" className="w-full shrink-0 border-b border-[var(--color-border)] px-3 py-2 md:w-56 md:border-b-0 md:border-r md:py-6">
          <ul className="flex gap-1 overflow-x-auto pb-1 md:block md:space-y-1 md:overflow-visible md:pb-0">
            {NAV_ITEMS.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.to === "/"}
                  className={({ isActive }) =>
                    `block whitespace-nowrap rounded-md px-3 py-2 text-sm ${
                      isActive
                        ? "bg-[var(--color-surface)] text-[var(--color-text-primary)]"
                        : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        <main id="main-content" tabIndex={-1} className="page-enter min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</main>
      </div>
    </div>
  );
}

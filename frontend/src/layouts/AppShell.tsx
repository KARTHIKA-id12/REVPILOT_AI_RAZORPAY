import { useState, useRef, useEffect } from "react";
import { NavLink, Link } from "react-router-dom";
import { SystemStatusBadge } from "../components/SystemStatusBadge";
import { useMerchant } from "../app/MerchantContext";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import { Bell, CheckCircle2, ShieldAlert, X } from "lucide-react";

const NAV_ITEMS = [
  { label: "Dashboard", to: "/" },
  { label: "Mission Workflow", to: "/mission" },
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
  const [showNotifications, setShowNotifications] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Fetch recent notifications via audit ledger
  const { data: auditData } = useQuery({
    queryKey: ["header-notifications", merchant?.id],
    queryFn: () => apiFetch<{ items: any[] }>(`/api/v1/audit?merchant_id=${merchant?.id}&page_size=10`),
    enabled: Boolean(merchant?.id),
    refetchInterval: 5000,
  });

  const notifications = (auditData?.items || []).filter((item: any) =>
    ["CREATE_CAMPAIGN_DRAFT", "CREATE_DISCOUNT", "CREATE_PAYMENT_LINK"].includes(item.action)
  );

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowNotifications(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

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
        <div className="flex items-center gap-4">
          {/* Notification Bell Dropdown */}
          <div className="relative" ref={dropdownRef}>
            <button
              type="button"
              onClick={() => setShowNotifications(!showNotifications)}
              className="relative rounded-full p-2 text-[var(--color-text-secondary)] hover:bg-[var(--color-surface)] hover:text-[var(--color-text-primary)] transition-colors"
              aria-label="Notifications"
            >
              <Bell size={20} />
              {notifications.length > 0 && (
                <span className="absolute top-1 right-1 flex h-4 w-4 items-center justify-center rounded-full bg-[var(--color-accent)] text-[10px] font-bold text-[#1a1200]">
                  {notifications.length}
                </span>
              )}
            </button>

            {showNotifications && (
              <div className="absolute right-0 mt-2 w-80 sm:w-96 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 shadow-xl z-50">
                <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-3">
                  <div className="flex items-center gap-2 font-semibold text-sm">
                    <Bell size={16} className="text-[var(--color-accent)]" />
                    <span>Notifications & Alerts</span>
                  </div>
                  <button
                    onClick={() => setShowNotifications(false)}
                    className="text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
                  >
                    <X size={16} />
                  </button>
                </div>

                <div className="mt-3 max-h-80 overflow-y-auto space-y-2">
                  {notifications.length === 0 ? (
                    <p className="py-6 text-center text-xs text-[var(--color-text-secondary)]">
                      No new notifications.
                    </p>
                  ) : (
                    notifications.map((n: any, idx: number) => (
                      <div
                        key={idx}
                        className="flex items-start gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3 text-xs"
                      >
                        <div className="mt-0.5 shrink-0">
                          {n.result === "success" ? (
                            <CheckCircle2 size={16} className="text-green-500" />
                          ) : (
                            <ShieldAlert size={16} className="text-[var(--color-warning)]" />
                          )}
                        </div>
                        <div className="flex-1">
                          <p className="font-semibold text-[var(--color-text-primary)]">
                            {n.action === "CREATE_CAMPAIGN_DRAFT" && "Campaign Drafted"}
                            {n.action === "CREATE_DISCOUNT" && "Approval Required"}
                            {n.action === "CREATE_PAYMENT_LINK" && "Payment Link Generated"}
                          </p>
                          <p className="mt-0.5 text-[var(--color-text-secondary)]">
                            {n.input_summary} — {n.reason}
                          </p>
                          <div className="mt-1 flex items-center justify-between text-[10px] text-[var(--color-text-secondary)]">
                            <span>{new Date(n.timestamp).toLocaleTimeString()}</span>
                            {n.action === "CREATE_DISCOUNT" && n.result === "pending_approval" && (
                              <Link
                                to="/approvals"
                                onClick={() => setShowNotifications(false)}
                                className="font-bold text-[var(--color-accent)] hover:underline"
                              >
                                Review Request &rarr;
                              </Link>
                            )}
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

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

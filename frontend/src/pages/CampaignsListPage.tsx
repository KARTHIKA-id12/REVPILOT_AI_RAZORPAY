import { useState } from "react";
import { Link } from "react-router-dom";
import { useMerchant } from "../app/MerchantContext";
import { useCampaigns } from "../services/campaigns";
import { EmptyState, ErrorState } from "../components/EmptyState";
import { formatCurrency, formatPercent } from "../lib/format";

const STATUS_FILTERS = ["all", "draft", "pending_approval", "approved", "running", "paused", "completed", "cancelled", "failed"];

const STATUS_COLORS: Record<string, string> = {
  draft: "text-[var(--color-text-secondary)]",
  pending_approval: "text-[var(--color-warning)]",
  approved: "text-[var(--color-info)]",
  running: "text-[var(--color-success)]",
  paused: "text-[var(--color-warning)]",
  completed: "text-[var(--color-success)]",
  cancelled: "text-[var(--color-text-secondary)]",
  failed: "text-[var(--color-danger)]",
};

export function CampaignsListPage() {
  const { merchant } = useMerchant();
  const [statusFilter, setStatusFilter] = useState("all");
  const { data, isLoading, isError } = useCampaigns(merchant?.id, statusFilter === "all" ? undefined : statusFilter);

  return (
    <div>
      <h1 className="text-2xl font-semibold">Campaigns</h1>
      <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
        Every campaign here went through policy checks, permission gates, and — unless explicitly configured
        otherwise — your approval before anything executed.
      </p>

      <div className="mt-6 flex flex-wrap gap-2">
        {STATUS_FILTERS.map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`rounded-full border px-3 py-1 text-xs ${
              statusFilter === s ? "border-[var(--color-accent)] text-[var(--color-accent)]" : "border-[var(--color-border)] text-[var(--color-text-secondary)]"
            }`}
          >
            {s.replace(/_/g, " ")}
          </button>
        ))}
      </div>

      <div className="mt-6 overflow-hidden rounded-xl border border-[var(--color-border)]">
        {isLoading ? (
          <div className="p-6 text-center text-xs text-[var(--color-text-secondary)]">Loading…</div>
        ) : isError ? (
          <ErrorState message="Couldn't load campaigns." />
        ) : data && data.items.length > 0 ? (
          <table className="w-full text-sm">
            <thead className="bg-[var(--color-surface)] text-left text-[10px] uppercase tracking-wide text-[var(--color-text-secondary)]">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Discount</th>
                <th className="px-4 py-3">Budget</th>
                <th className="px-4 py-3">Expected revenue</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)] bg-[var(--color-bg)]">
              {data.items.map((c) => (
                <tr key={c.id} className="hover:bg-[var(--color-surface)]">
                  <td className="px-4 py-3">
                    <Link to={`/campaigns/${c.id}`} className="text-[var(--color-text-primary)] hover:text-[var(--color-accent)]">
                      {c.name}
                    </Link>
                  </td>
                  <td className={`px-4 py-3 font-medium ${STATUS_COLORS[c.status] ?? ""}`}>{c.status.replace(/_/g, " ")}</td>
                  <td className="px-4 py-3 font-mono">{formatPercent(c.discount_percent / 100)}</td>
                  <td className="px-4 py-3 font-mono">{formatCurrency(c.budget_amount)}</td>
                  <td className="px-4 py-3 font-mono">{formatCurrency(c.expected_revenue_amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState
            title="No campaigns yet"
            description="Ask the AI Growth Agent to create one from your top opportunity, or check the Approval Center."
          />
        )}
      </div>
    </div>
  );
}

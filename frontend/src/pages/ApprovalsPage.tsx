import { useState } from "react";
import { useMerchant } from "../app/MerchantContext";
import { useApprovals, useDecideApproval } from "../services/approvals";
import { EmptyState, ErrorState } from "../components/EmptyState";
import { RiskBadge } from "../components/RiskBadge";
import { formatCurrency } from "../lib/format";
import type { ApprovalRequestItem } from "../types/api";

function ApprovalCard({ approval }: { approval: ApprovalRequestItem }) {
  const { merchant } = useMerchant();
  const decide = useDecideApproval(merchant?.id);
  const sim = approval.payload.simulation;

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-full border border-[var(--color-border)] px-2 py-0.5 text-[10px] uppercase tracking-wide text-[var(--color-text-secondary)]">
              {approval.action_code.replace(/_/g, " ")}
            </span>
            <RiskBadge level={approval.risk_level} />
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] uppercase font-bold tracking-wide ${
                approval.status === "approved"
                  ? "bg-green-500/10 text-green-500 border border-green-500/20"
                  : approval.status === "rejected"
                  ? "bg-red-500/10 text-red-500 border border-red-500/20"
                  : "bg-amber-500/10 text-amber-500 border border-amber-500/20"
              }`}
            >
              {approval.status}
            </span>
          </div>
          <h3 className="mt-1.5 text-base font-medium">
            Discount campaign — {approval.payload.discount_percent}% off, budget {formatCurrency(approval.payload.budget_amount ?? 0)}
          </h3>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs font-medium ${approval.policy_result.passed ? "text-[var(--color-success)]" : "text-[var(--color-danger)]"}`}>
            Policy {approval.policy_result.passed ? "PASSED" : "FAILED"}
          </span>
        </div>
      </div>

      {sim && (
        <div className="mt-4 grid grid-cols-2 gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4 text-xs sm:grid-cols-4">
          <Stat label="Reach" value={String(sim.eligible_customers)} />
          <Stat label="Expected revenue" value={formatCurrency(sim.expected_revenue)} sublabel="ESTIMATED" />
          <Stat label="Discount cost" value={formatCurrency(sim.discount_cost)} />
          <Stat label="ROI" value={sim.roi !== null ? `${sim.roi.toFixed(1)}×` : "undefined"} />
        </div>
      )}

      <div className="mt-4 flex items-center justify-between">
        <span className="text-xs text-[var(--color-text-secondary)]">
          Requested {approval.created_at ? new Date(approval.created_at).toLocaleString() : "—"}
        </span>
        {approval.status === "pending" ? (
          <div className="flex gap-2">
            <button
              onClick={() => decide.mutate({ approvalId: approval.id, decision: "reject" })}
              disabled={decide.isPending}
              className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-[var(--color-text-secondary)] hover:border-[var(--color-danger)] hover:text-[var(--color-danger)] disabled:opacity-50"
            >
              Reject
            </button>
            <button
              onClick={() => decide.mutate({ approvalId: approval.id, decision: "approve" })}
              disabled={decide.isPending}
              className="rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-xs font-medium text-[#1a1200] disabled:opacity-50"
            >
              {decide.isPending ? "Processing…" : "Approve"}
            </button>
          </div>
        ) : (
          <span className="text-xs text-[var(--color-text-secondary)] capitalize font-medium">
            Status: {approval.status}
          </span>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, sublabel }: { label: string; value: string; sublabel?: string }) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-wide text-[var(--color-text-secondary)]">{label}</div>
      <div className="mt-0.5 font-mono text-[var(--color-text-primary)]">{value}</div>
      {sublabel && <div className="text-[8px] uppercase tracking-wide text-[var(--color-warning)]">{sublabel}</div>}
    </div>
  );
}

export function ApprovalsPage() {
  const { merchant } = useMerchant();
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const { data, isLoading, isError } = useApprovals(merchant?.id, filterStatus);

  const TABS = [
    { id: "all", label: "All Requests" },
    { id: "pending", label: "Pending Sign-off" },
    { id: "approved", label: "Approved" },
    { id: "rejected", label: "Rejected" },
  ];

  return (
    <div>
      <h1 className="text-2xl font-semibold">Approval Center</h1>
      <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
        Financial actions the agent has proposed, gated by your policies and permissions. Nothing here has touched
        Razorpay yet — approving is what authorizes execution.
      </p>

      {/* Status Filter Tabs */}
      <div className="mt-6 flex gap-2 border-b border-[var(--color-border)] pb-3">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setFilterStatus(tab.id)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
              filterStatus === tab.id
                ? "bg-[var(--color-accent)] text-[#1a1200]"
                : "bg-[var(--color-surface)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] border border-[var(--color-border)]"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="mt-6 space-y-4">
        {isLoading ? (
          Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="h-32 animate-pulse rounded-xl bg-[var(--color-border)]" />
          ))
        ) : isError ? (
          <ErrorState message="Couldn't load approvals." />
        ) : data && data.items.length > 0 ? (
          data.items.map((a) => <ApprovalCard key={a.id} approval={a} />)
        ) : (
          <EmptyState
            title="No approval records found"
            description="When the agent proposes a discount, payment link, or order that requires sign-off, it will show up here."
          />
        )}
      </div>
    </div>
  );
}

import { Link, useParams } from "react-router-dom";
import { useCampaign, useCampaignAction } from "../services/campaigns";
import { ErrorState } from "../components/EmptyState";
import { formatCurrency, formatPercent } from "../lib/format";

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

const RESULT_COLORS: Record<string, string> = {
  success: "text-[var(--color-success)]",
  blocked: "text-[var(--color-danger)]",
  failed: "text-[var(--color-danger)]",
  pending_approval: "text-[var(--color-warning)]",
  recovered: "text-[var(--color-info)]",
};

function Stat({ label, value, sublabel }: { label: string; value: string; sublabel?: string }) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-secondary)]">{label}</div>
      <div className="mt-1.5 text-lg font-semibold">{value}</div>
      {sublabel && <div className="mt-0.5 text-[9px] uppercase tracking-wide text-[var(--color-warning)]">{sublabel}</div>}
    </div>
  );
}

export function CampaignDetailPage() {
  const { campaignId } = useParams<{ campaignId: string }>();
  const { data: campaign, isLoading, isError } = useCampaign(campaignId);
  const action = useCampaignAction(campaignId);

  if (isLoading) {
    return <div className="text-sm text-[var(--color-text-secondary)]">Loading campaign…</div>;
  }

  if (isError || !campaign) {
    return <ErrorState message="Campaign not found." />;
  }

  return (
    <div>
      <Link to="/campaigns" className="text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]">
        ← All campaigns
      </Link>

      <div className="mt-3 flex items-start justify-between gap-6">
        <div>
          <span className={`text-xs font-semibold uppercase tracking-wide ${STATUS_COLORS[campaign.status] ?? ""}`}>
            {campaign.status.replace(/_/g, " ")}
          </span>
          <h1 className="mt-1 text-2xl font-semibold">{campaign.name}</h1>
          <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
            {campaign.products.map((p) => p.name).join(" → ") || campaign.objective}
          </p>
        </div>
        <div className="flex gap-2">
          {campaign.status === "running" && (
            <button
              onClick={() => action.mutate("pause")}
              disabled={action.isPending}
              className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-[var(--color-text-secondary)] hover:border-[var(--color-warning)] hover:text-[var(--color-warning)] disabled:opacity-50"
            >
              Pause
            </button>
          )}
          {["draft", "pending_approval", "approved", "running", "paused"].includes(campaign.status) && (
            <button
              onClick={() => action.mutate("cancel")}
              disabled={action.isPending}
              className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-[var(--color-text-secondary)] hover:border-[var(--color-danger)] hover:text-[var(--color-danger)] disabled:opacity-50"
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Discount" value={formatPercent(campaign.discount_percent / 100)} />
        <Stat label="Budget" value={formatCurrency(campaign.budget_amount)} />
        <Stat label="Expected revenue" value={formatCurrency(campaign.expected_revenue_amount)} sublabel="ESTIMATED" />
        <Stat label="Actual revenue" value={formatCurrency(campaign.actual_revenue_amount)} sublabel="ATTRIBUTED" />
      </div>

      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="text-sm font-medium text-[var(--color-text-secondary)]">Approval history</h2>
          {campaign.approval_history.length === 0 ? (
            <p className="mt-3 text-xs text-[var(--color-text-secondary)]">No approval was required for this campaign.</p>
          ) : (
            <div className="mt-3 space-y-3">
              {campaign.approval_history.map((a) => (
                <div key={a.id} className="border-b border-[var(--color-border)] pb-3 text-xs last:border-0">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-[var(--color-text-primary)]">{a.status}</span>
                    <span className="text-[var(--color-text-secondary)]">{a.risk_level} risk</span>
                  </div>
                  <div className="mt-1 text-[var(--color-text-secondary)]">
                    Policy: {a.policy_result.passed ? "passed" : `failed (${a.policy_result.violations.join(", ")})`}
                  </div>
                  <div className="mt-1 font-mono text-[10px] text-[var(--color-text-secondary)]">
                    Requested {a.created_at ? new Date(a.created_at).toLocaleString() : "—"}
                    {a.decided_at && ` · Decided ${new Date(a.decided_at).toLocaleString()}`}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="text-sm font-medium text-[var(--color-text-secondary)]">Payment links</h2>
          {campaign.payments.length === 0 ? (
            <p className="mt-3 text-xs text-[var(--color-text-secondary)]">No payment has been created yet.</p>
          ) : (
            <div className="mt-3 space-y-3">
              {campaign.payments.map((p) => (
                <div key={p.id} className="border-b border-[var(--color-border)] pb-3 text-xs last:border-0">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-[var(--color-text-primary)]">{formatCurrency(p.amount)}</span>
                    <span className="rounded-full border border-[var(--color-border)] px-2 py-0.5 text-[9px] uppercase tracking-wide text-[var(--color-text-secondary)]">
                      {p.provider === "mock" ? "Demo Payment Mode" : "Razorpay Test Mode"}
                    </span>
                  </div>
                  <div className="mt-1 text-[var(--color-text-secondary)]">Status: {p.status}</div>
                  <div className="mt-1 font-mono text-[10px] text-[var(--color-text-secondary)]">
                    {p.created_at ? new Date(p.created_at).toLocaleString() : "—"}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <h2 className="text-sm font-medium text-[var(--color-text-secondary)]">Audit trail</h2>
        {campaign.audit_trail.length === 0 ? (
          <p className="mt-3 text-xs text-[var(--color-text-secondary)]">No audit events yet.</p>
        ) : (
          <div className="mt-3 space-y-2 font-mono text-xs">
            {campaign.audit_trail.map((e, i) => (
              <div key={i} className="flex items-start gap-3 border-b border-[var(--color-border)] pb-2 last:border-0">
                <span className="w-40 shrink-0 text-[var(--color-text-secondary)]">
                  {e.created_at ? new Date(e.created_at).toLocaleString() : "—"}
                </span>
                <span className="w-44 shrink-0">{e.action}</span>
                <span className={`w-20 shrink-0 uppercase ${RESULT_COLORS[e.result] ?? ""}`}>{e.result}</span>
                <span className="text-[var(--color-text-secondary)]">{e.reason ?? e.error ?? ""}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

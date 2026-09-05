import { useParams, Link } from "react-router-dom";
import { useOpportunity } from "../services/opportunities";
import { RiskBadge, OpportunityTypeBadge } from "../components/RiskBadge";
import { ErrorState } from "../components/EmptyState";
import { formatCurrency, formatMultiplier, formatPercent } from "../lib/format";

const EVIDENCE_LABELS: Record<string, string> = {
  customers_bought_source: "Customers who bought the source product",
  customers_bought_both: "Customers who bought both",
  support: "Support (share of all orders containing both)",
  confidence_organic: "Organic confidence (source → target)",
  lift: "Lift vs. baseline",
  target_stock_status: "Target product stock status",
  abandoned_sessions: "Abandoned cart sessions",
  segment_customer_count: "Customers in this segment",
  avg_historical_order_value: "Average historical order value",
  one_time_buyers_overdue_for_reorder: "One-time buyers overdue for reorder",
  min_days_since_last_purchase: "Minimum days since last purchase",
  segment_code: "Segment",
};

function formatEvidenceValue(key: string, value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (key === "support" || key === "confidence_organic") return formatPercent(Number(value), 1);
  if (key === "lift") return formatMultiplier(Number(value));
  if (key === "avg_historical_order_value") return formatCurrency(Number(value));
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

export function OpportunityDetailPage() {
  const { opportunityId } = useParams<{ opportunityId: string }>();
  const { data: opportunity, isLoading, isError } = useOpportunity(opportunityId);

  if (isLoading) {
    return <div className="text-sm text-[var(--color-text-secondary)]">Loading opportunity…</div>;
  }

  if (isError || !opportunity) {
    return <ErrorState message="Opportunity not found." />;
  }

  const title = opportunity.source_product && opportunity.target_product
    ? `${opportunity.source_product.name} → ${opportunity.target_product.name}`
    : (opportunity.target_product?.name ?? opportunity.source_product?.name ?? "Opportunity");

  const evidenceEntries = Object.entries(opportunity.evidence).filter(([key]) => key !== "assumption");
  const assumption = opportunity.evidence.assumption as string | undefined;

  return (
    <div>
      <Link to="/opportunities" className="text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]">
        ← All opportunities
      </Link>

      <div className="mt-3 flex items-start justify-between gap-6">
        <div>
          <div className="flex items-center gap-2">
            <OpportunityTypeBadge type={opportunity.type} />
            <RiskBadge level={opportunity.risk_level} />
          </div>
          <h1 className="mt-2 text-2xl font-semibold">{title}</h1>
        </div>
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-right">
          <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-secondary)]">Priority score</div>
          <div className="text-2xl font-semibold text-[var(--color-accent)]">{opportunity.priority_score.toFixed(0)}</div>
          <Link
            to={`/simulator/${opportunity.id}`}
            className="mt-2 block rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-center text-xs font-medium text-[#1a1200]"
          >
            Simulate
          </Link>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Customers reached" value={String(opportunity.reach_count)} />
        <Stat label="Historical affinity" value={opportunity.historical_affinity > 0 ? formatMultiplier(opportunity.historical_affinity) : "—"} />
        <Stat label="Estimated conversion" value={formatPercent(opportunity.estimated_conversion)} sublabel="ESTIMATED" />
        <Stat label="Estimated incremental revenue" value={formatCurrency(opportunity.estimated_revenue_amount)} sublabel="ESTIMATED" tone="accent" />
      </div>

      <div className="mt-8 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <h2 className="text-sm font-medium text-[var(--color-text-secondary)]">Why this opportunity?</h2>
        <dl className="mt-4 grid grid-cols-1 gap-x-8 gap-y-3 sm:grid-cols-2">
          {evidenceEntries.map(([key, value]) => (
            <div key={key} className="flex items-baseline justify-between border-b border-[var(--color-border)] pb-2 text-sm">
              <dt className="text-[var(--color-text-secondary)]">{EVIDENCE_LABELS[key] ?? key}</dt>
              <dd className="font-mono text-[var(--color-text-primary)]">{formatEvidenceValue(key, value)}</dd>
            </div>
          ))}
        </dl>

        {assumption && (
          <div className="mt-5 rounded-lg border border-[var(--color-warning)]/30 bg-[var(--color-warning)]/5 px-4 py-3">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-warning)]">Assumption behind this estimate</div>
            <p className="mt-1 text-xs text-[var(--color-text-secondary)]">{assumption}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, sublabel, tone }: { label: string; value: string; sublabel?: string; tone?: "accent" }) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-secondary)]">{label}</div>
      <div className={`mt-1.5 text-lg font-semibold ${tone === "accent" ? "text-[var(--color-accent)]" : ""}`}>{value}</div>
      {sublabel && <div className="mt-0.5 text-[9px] uppercase tracking-wide text-[var(--color-text-secondary)]">{sublabel}</div>}
    </div>
  );
}

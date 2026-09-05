import { Link } from "react-router-dom";
import type { Opportunity } from "../types/api";
import { formatCurrency, formatMultiplier, formatPercent } from "../lib/format";
import { OpportunityTypeBadge, RiskBadge } from "./RiskBadge";

function priorityLabel(score: number): { label: string; color: string } {
  if (score >= 70) return { label: "HIGH", color: "var(--color-accent)" };
  if (score >= 40) return { label: "MEDIUM", color: "var(--color-warning)" };
  return { label: "LOW", color: "var(--color-text-secondary)" };
}

export function OpportunityCard({ opportunity }: { opportunity: Opportunity }) {
  const priority = priorityLabel(opportunity.priority_score);
  const title = opportunity.source_product && opportunity.target_product
    ? `${opportunity.source_product.name} → ${opportunity.target_product.name}`
    : (opportunity.target_product?.name ?? opportunity.source_product?.name ?? "Opportunity");

  return (
    <Link
      to={`/opportunities/${opportunity.id}`}
      className="block rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 transition-colors hover:border-[var(--color-accent)]"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold tracking-wide" style={{ color: priority.color }}>
              {priority.label}
            </span>
            <OpportunityTypeBadge type={opportunity.type} />
          </div>
          <h3 className="mt-1.5 text-base font-medium">{title}</h3>
        </div>
        <div className="text-right">
          <div className="text-lg font-semibold text-[var(--color-accent)]">
            {formatCurrency(opportunity.estimated_revenue_amount)}
          </div>
          <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-secondary)]">Estimated</div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-xs text-[var(--color-text-secondary)]">
        <span>{opportunity.reach_count} customers</span>
        {opportunity.historical_affinity > 0 && <span>{formatMultiplier(opportunity.historical_affinity)} affinity</span>}
        <span>{formatPercent(opportunity.estimated_conversion)} est. conversion</span>
        <RiskBadge level={opportunity.risk_level} />
      </div>
    </Link>
  );
}

export function OpportunityCardSkeleton() {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <div className="h-3 w-16 animate-pulse rounded bg-[var(--color-border)]" />
      <div className="mt-2 h-5 w-48 animate-pulse rounded bg-[var(--color-border)]" />
      <div className="mt-4 h-3 w-64 animate-pulse rounded bg-[var(--color-border)]" />
    </div>
  );
}

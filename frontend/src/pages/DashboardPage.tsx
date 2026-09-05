import { Link } from "react-router-dom";
import { useMerchant } from "../app/MerchantContext";
import { useDashboardSummary, useRevenueTrend, useTopProducts } from "../services/dashboard";
import { useOpportunities } from "../services/opportunities";
import { MetricCard, MetricCardSkeleton } from "../components/MetricCard";
import { RevenueTrendChart } from "../components/RevenueTrendChart";
import { OpportunityCard, OpportunityCardSkeleton } from "../components/OpportunityCard";
import { EmptyState, ErrorState } from "../components/EmptyState";
import { formatCurrency, formatPercent } from "../lib/format";

export function DashboardPage() {
  const { merchant, isLoading: merchantLoading } = useMerchant();
  const merchantId = merchant?.id;

  const summary = useDashboardSummary(merchantId);
  const trend = useRevenueTrend(merchantId);
  const topProducts = useTopProducts(merchantId, 5);
  const opportunities = useOpportunities(merchantId, { pageSize: 3 });

  if (merchantLoading) {
    return <div className="text-sm text-[var(--color-text-secondary)]">Loading merchant…</div>;
  }

  if (!merchant) {
    return (
      <ErrorState message="No merchant found. Run `python scripts/seed_demo.py` to create the TechNest demo merchant." />
    );
  }

  return (
    <div className="mx-auto max-w-[1440px]">
      <h1 className="text-2xl font-semibold">Command Center</h1>
      <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
        Find revenue. Explain the opportunity. Act safely. Measure the result.
      </p>

      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {summary.isLoading ? (
          Array.from({ length: 4 }).map((_, i) => <MetricCardSkeleton key={i} />)
        ) : summary.isError || !summary.data ? (
          <div className="col-span-4">
            <ErrorState message="Couldn't load revenue metrics." />
          </div>
        ) : (
          <>
            <MetricCard label="Total Revenue" value={formatCurrency(summary.data.total_revenue)} sublabel={`${summary.data.order_count} paid orders`} />
            <MetricCard label="Average Order Value" value={formatCurrency(summary.data.average_order_value)} />
            <MetricCard label="Repeat Purchase Rate" value={formatPercent(summary.data.repeat_purchase_rate)} tone="positive" />
            <MetricCard label="Open Opportunities" value={String(summary.data.open_opportunities)} sublabel="Detected by the analytics engine" />
          </>
        )}
      </div>

      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="card-hover rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6 lg:col-span-2">
          <h2 className="text-sm font-medium text-[var(--color-text-secondary)]">Revenue trend</h2>
          {trend.isLoading ? (
            <div className="mt-4 h-[220px] animate-pulse rounded-lg bg-[var(--color-border)]" />
          ) : trend.data && trend.data.points.length > 0 ? (
            <div className="mt-2">
              <RevenueTrendChart points={trend.data.points} />
            </div>
          ) : (
            <div className="mt-4">
              <EmptyState title="No revenue yet" description="Once orders are paid, weekly revenue will chart here." />
            </div>
          )}
        </div>

        <div className="card-hover rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 sm:p-6">
          <h2 className="text-sm font-medium text-[var(--color-text-secondary)]">Top products</h2>
          <div className="mt-4 space-y-3">
            {topProducts.isLoading ? (
              Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-8 animate-pulse rounded bg-[var(--color-border)]" />)
            ) : topProducts.data && topProducts.data.products.length > 0 ? (
              topProducts.data.products.map((p) => (
                <div key={p.product_id} className="flex items-center justify-between text-sm">
                  <span className="truncate pr-3">{p.name}</span>
                  <span className="shrink-0 font-medium text-[var(--color-text-primary)]">{formatCurrency(p.revenue)}</span>
                </div>
              ))
            ) : (
              <p className="text-xs text-[var(--color-text-secondary)]">No paid orders yet.</p>
            )}
          </div>
        </div>
      </div>

      <div className="mt-8">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-[var(--color-text-secondary)]">Top opportunities</h2>
          <Link to="/opportunities" className="text-xs text-[var(--color-accent)] hover:underline">
            View all →
          </Link>
        </div>
        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
          {opportunities.isLoading ? (
            Array.from({ length: 3 }).map((_, i) => <OpportunityCardSkeleton key={i} />)
          ) : opportunities.data && opportunities.data.items.length > 0 ? (
            opportunities.data.items.map((opp) => <OpportunityCard key={opp.id} opportunity={opp} />)
          ) : (
            <div className="lg:col-span-3">
              <EmptyState
                title="No revenue opportunities yet"
                description="Run your first commerce analysis to detect cross-sell, bundle, and reactivation opportunities."
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

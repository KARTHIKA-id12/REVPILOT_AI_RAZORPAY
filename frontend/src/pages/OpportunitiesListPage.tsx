import { useState } from "react";
import { useMerchant } from "../app/MerchantContext";
import { useOpportunities, useRefreshOpportunities } from "../services/opportunities";
import { OpportunityCard, OpportunityCardSkeleton } from "../components/OpportunityCard";
import { EmptyState, ErrorState } from "../components/EmptyState";
import type { OpportunityType } from "../types/api";

const TYPE_FILTERS: { value: OpportunityType | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "cross_sell", label: "Cross-sell" },
  { value: "bundle", label: "Bundle" },
  { value: "abandoned_cart", label: "Abandoned cart" },
  { value: "reactivation", label: "Reactivation" },
  { value: "repeat_purchase", label: "Repeat purchase" },
];

export function OpportunitiesListPage() {
  const { merchant } = useMerchant();
  const [typeFilter, setTypeFilter] = useState<OpportunityType | "all">("all");

  const opportunities = useOpportunities(merchant?.id, {
    type: typeFilter === "all" ? undefined : typeFilter,
    pageSize: 30,
  });
  const refresh = useRefreshOpportunities(merchant?.id);

  return (
    <div>
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Revenue Opportunities</h1>
          <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
            Detected by the analytics engine from real orders, carts, and customer behavior — nothing here is guessed.
          </p>
        </div>
        <button
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
          className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-[var(--color-text-primary)] hover:border-[var(--color-accent)] disabled:opacity-50"
        >
          {refresh.isPending ? "Analyzing…" : "Re-run analysis"}
        </button>
      </div>

      <div className="mt-6 flex flex-wrap gap-2">
        {TYPE_FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setTypeFilter(f.value)}
            className={`rounded-full border px-3 py-1 text-xs ${
              typeFilter === f.value
                ? "border-[var(--color-accent)] text-[var(--color-accent)]"
                : "border-[var(--color-border)] text-[var(--color-text-secondary)]"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        {opportunities.isLoading ? (
          Array.from({ length: 6 }).map((_, i) => <OpportunityCardSkeleton key={i} />)
        ) : opportunities.isError ? (
          <div className="lg:col-span-2">
            <ErrorState message="Couldn't load opportunities." />
          </div>
        ) : opportunities.data && opportunities.data.items.length > 0 ? (
          opportunities.data.items.map((opp) => <OpportunityCard key={opp.id} opportunity={opp} />)
        ) : (
          <div className="lg:col-span-2">
            <EmptyState
              title="No opportunities in this category"
              description="Try a different filter, or re-run the analysis if you've just seeded new data."
            />
          </div>
        )}
      </div>
    </div>
  );
}

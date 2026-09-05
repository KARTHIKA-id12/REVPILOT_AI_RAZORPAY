import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMerchant } from "../app/MerchantContext";
import { useOpportunity } from "../services/opportunities";
import { useCompareSimulation } from "../services/simulation";
import { EmptyState, ErrorState } from "../components/EmptyState";
import { formatCurrency, formatPercent } from "../lib/format";
import type { SimulationScenario } from "../types/api";

const DEFAULT_DISCOUNTS = [5, 10, 15, 20];

function ScenarioCard({ scenario, isRecommended }: { scenario: SimulationScenario; isRecommended: boolean }) {
  return (
    <div
      className={`rounded-xl border p-5 ${
        isRecommended ? "border-[var(--color-accent)] bg-[var(--color-accent)]/5" : "border-[var(--color-border)] bg-[var(--color-surface)]"
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="text-lg font-semibold">{scenario.discount_percent}% discount</div>
        {isRecommended && (
          <span className="rounded-full bg-[var(--color-accent)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#1a1200]">
            Best ROI
          </span>
        )}
      </div>

      <dl className="mt-4 space-y-2.5 text-sm">
        <Row label="Expected orders" value={scenario.expected_orders.toFixed(1)} />
        <Row label="Expected revenue" value={formatCurrency(scenario.expected_revenue)} sublabel="ESTIMATED" />
        <Row label="Discount cost" value={formatCurrency(scenario.discount_cost)} />
        <Row label="Expected incremental revenue" value={formatCurrency(scenario.expected_incremental_revenue)} sublabel="ESTIMATED" />
        <Row label="ROI" value={scenario.roi !== null ? `${scenario.roi.toFixed(1)}×` : "undefined"} emphasize />
      </dl>
    </div>
  );
}

function Row({ label, value, sublabel, emphasize }: { label: string; value: string; sublabel?: string; emphasize?: boolean }) {
  return (
    <div className="flex items-baseline justify-between border-b border-[var(--color-border)] pb-2">
      <dt className="text-[var(--color-text-secondary)]">{label}</dt>
      <dd className={`font-mono ${emphasize ? "text-base font-semibold text-[var(--color-accent)]" : "text-[var(--color-text-primary)]"}`}>
        {value}
        {sublabel && <span className="ml-1.5 text-[9px] uppercase tracking-wide text-[var(--color-warning)]">{sublabel}</span>}
      </dd>
    </div>
  );
}

export function SimulatorPage() {
  const { opportunityId } = useParams<{ opportunityId: string }>();
  const { merchant } = useMerchant();
  const { data: opportunity, isLoading: oppLoading } = useOpportunity(opportunityId);
  const compare = useCompareSimulation();
  const [customDiscount, setCustomDiscount] = useState("");
  const [discounts, setDiscounts] = useState<number[]>(DEFAULT_DISCOUNTS);

  useEffect(() => {
    if (merchant?.id && opportunityId) {
      compare.mutate({ merchantId: merchant.id, opportunityId, discountPercents: discounts });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [merchant?.id, opportunityId, discounts]);

  function addCustomDiscount() {
    const pct = Number(customDiscount);
    if (!Number.isNaN(pct) && pct >= 0 && pct <= 100 && !discounts.includes(pct)) {
      setDiscounts([...discounts, pct].sort((a, b) => a - b));
      setCustomDiscount("");
    }
  }

  if (!opportunityId) {
    return <ErrorState message="No opportunity selected." />;
  }

  if (oppLoading) {
    return <div className="text-sm text-[var(--color-text-secondary)]">Loading…</div>;
  }

  const title = opportunity?.source_product && opportunity?.target_product
    ? `${opportunity.source_product.name} → ${opportunity.target_product.name}`
    : (opportunity?.target_product?.name ?? "Campaign");

  return (
    <div>
      <Link to={`/opportunities/${opportunityId}`} className="text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]">
        ← Back to opportunity
      </Link>

      <h1 className="mt-3 text-2xl font-semibold">Simulate: {title}</h1>
      <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
        Every scenario below is computed from real transaction data with the exact same deterministic formula — no
        LLM involved, same inputs always produce the same output.
      </p>

      <div className="mt-4 flex items-center gap-2">
        <input
          type="number"
          min={0}
          max={100}
          value={customDiscount}
          onChange={(e) => setCustomDiscount(e.target.value)}
          placeholder="Add discount %"
          className="w-36 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm outline-none focus:border-[var(--color-accent)]"
        />
        <button
          onClick={addCustomDiscount}
          className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-[var(--color-text-secondary)] hover:border-[var(--color-accent)] hover:text-[var(--color-text-primary)]"
        >
          Add scenario
        </button>
      </div>

      <div className="mt-6">
        {compare.isPending ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {discounts.map((d) => (
              <div key={d} className="h-56 animate-pulse rounded-xl bg-[var(--color-border)]" />
            ))}
          </div>
        ) : compare.isError ? (
          <ErrorState message="Couldn't run the simulation." />
        ) : compare.data ? (
          <>
            <p className="mb-4 text-xs text-[var(--color-text-secondary)]">
              {compare.data.eligible_customers} eligible customers, {formatPercent(compare.data.organic_confidence)} organic confidence.
            </p>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {compare.data.scenarios.map((s) => (
                <ScenarioCard key={s.discount_percent} scenario={s} isRecommended={s.discount_percent === compare.data!.recommended_discount_percent} />
              ))}
            </div>
          </>
        ) : (
          <EmptyState title="No simulation yet" description="Add a discount scenario to see projected results." />
        )}
      </div>
    </div>
  );
}

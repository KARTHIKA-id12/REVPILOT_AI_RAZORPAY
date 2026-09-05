import { useState } from "react";
import { useMerchant } from "../app/MerchantContext";
import { EmptyState, ErrorState } from "../components/EmptyState";
import { useProducts } from "../services/merchantData";
import { formatCurrency } from "../lib/format";

export function ProductsPage() {
  const { merchant } = useMerchant();
  const [q, setQ] = useState("");
  const products = useProducts(merchant?.id, q);
  return (
    <div className="mx-auto max-w-[1440px]">
      <h1 className="text-2xl font-semibold">Products</h1>
      <p className="mt-1 text-sm text-[var(--color-text-secondary)]">Live catalog, pricing, and inventory availability.</p>
      <label className="mt-6 block max-w-md text-xs font-medium text-[var(--color-text-secondary)]">
        Search catalog
        <input value={q} onChange={(event) => setQ(event.target.value)} placeholder="Product name or SKU"
          className="mt-2 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text-primary)]" />
      </label>
      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {products.isLoading ? Array.from({ length: 6 }).map((_, i) => <div key={i} aria-hidden="true" className="h-32 animate-pulse rounded-xl bg-[var(--color-surface)]" />)
          : products.isError ? <div className="sm:col-span-2 xl:col-span-3"><ErrorState message="Couldn't load products." /></div>
          : products.data?.items.length ? products.data.items.map((product) => (
            <article key={product.id} className="card-hover rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
              <div className="flex items-start justify-between gap-3"><h2 className="font-medium">{product.name}</h2><span className={`rounded-full px-2 py-1 text-[10px] uppercase ${product.stock_status === "out_of_stock" ? "bg-[var(--color-danger)]/15 text-[var(--color-danger)]" : "bg-[var(--color-success)]/15 text-[var(--color-success)]"}`}>{product.stock_status.replace("_", " ")}</span></div>
              <p className="mt-1 font-mono text-xs text-[var(--color-text-secondary)]">{product.sku}</p>
              <div className="mt-6 flex items-end justify-between"><span className="text-lg font-semibold">{formatCurrency(product.price_amount)}</span><span className="text-xs text-[var(--color-text-secondary)]">{product.stock_qty} in stock</span></div>
            </article>
          )) : <div className="sm:col-span-2 xl:col-span-3"><EmptyState title="No products found" description="Try a different search or seed the TechNest demo catalog." /></div>}
      </div>
    </div>
  );
}
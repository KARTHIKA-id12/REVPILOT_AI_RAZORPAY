import { useMemo, useState } from "react";
import { ArrowRight, Bot, Plus, ShoppingBag, Sparkles, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import { useMerchant } from "../app/MerchantContext";
import { useBuyerCart, useBuyerCartAction, useBuyerQuery } from "../services/buyer";
import { formatCurrency } from "../lib/format";
import type { BuyerProduct, BuyerQueryResponse, CartState } from "../types/api";

const PROMPTS = [
  "I need a gaming setup under ₹5,000",
  "Find a comfortable office setup under ₹4,000",
  "Show me something for streaming",
];

function ProductTile({ product, onAdd }: { product: BuyerProduct; onAdd: (id: string) => void }) {
  return (
    <article className="rounded-2xl border border-[#e5ded2] bg-white p-4 shadow-[0_8px_24px_rgba(75,56,28,0.06)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#a17b47]">{product.category ?? "Product"}</div>
          <h3 className="mt-1 font-medium text-[#211b15]">{product.name}</h3>
        </div>
        <span className="rounded-full bg-[#edf6ec] px-2 py-1 text-[10px] font-medium text-[#397244]">In stock</span>
      </div>
      <p className="mt-3 line-clamp-2 text-xs leading-5 text-[#766d62]">{product.description}</p>
      <div className="mt-4 flex items-center justify-between">
        <span className="text-lg font-semibold text-[#211b15]">{formatCurrency(product.price.amount)}</span>
        <button
          onClick={() => onAdd(product.id)}
          className="inline-flex items-center gap-1.5 rounded-full bg-[#211b15] px-3 py-2 text-xs font-medium text-[#fffaf2] transition hover:bg-[#3a2e22]"
        >
          Add <Plus size={13} />
        </button>
      </div>
    </article>
  );
}

function CartPanel({ cart, onAction, busy }: { cart: CartState | undefined; onAction: (action: "remove" | "clear", productId?: string) => void; busy: boolean }) {
  return (
    <aside className="rounded-3xl border border-[#e5ded2] bg-[#fffaf2] p-5 shadow-[0_12px_32px_rgba(75,56,28,0.08)]">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShoppingBag size={17} className="text-[#a17b47]" />
          <h2 className="font-semibold text-[#211b15]">Your cart</h2>
        </div>
        <span className="text-xs text-[#766d62]">{cart?.item_count ?? 0} items</span>
      </div>
      {cart?.items.length ? (
        <>
          <div className="mt-5 space-y-3">
            {cart.items.map((item) => (
              <div key={item.id} className="flex items-center justify-between gap-3 border-b border-[#eee6da] pb-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-[#211b15]">{item.name}</div>
                  <div className="mt-1 text-xs text-[#766d62]">
                    {item.quantity} × {formatCurrency(item.unit_price.amount)}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="text-sm font-medium text-[#211b15]">{formatCurrency(item.line_total.amount)}</span>
                  <button
                    aria-label={`Remove ${item.name}`}
                    onClick={() => onAction("remove", item.product_id)}
                    className="rounded-full p-1.5 text-[#a17b47] hover:bg-[#f2e8d9]"
                    disabled={busy}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-5 flex items-center justify-between text-sm">
            <span className="text-[#766d62]">Total</span>
            <span className="text-xl font-semibold text-[#211b15]">{formatCurrency(cart.total.amount)}</span>
          </div>
          <button
            onClick={() => onAction("clear")}
            className="mt-4 text-xs text-[#a17b47] underline-offset-2 hover:underline"
            disabled={busy}
          >
            Clear cart
          </button>
          <div className="mt-4 rounded-xl bg-[#f1e9dc] px-3 py-2 text-[11px] leading-4 text-[#766d62]">
            Checkout will recompute prices and stock before asking for your explicit confirmation.
          </div>
          {cart.can_checkout && (
            <Link to="/shop/checkout" className="mt-4 block rounded-xl bg-[#211b15] px-4 py-3 text-center text-sm font-semibold text-[#fffaf2] hover:bg-[#3a2e22]">
              Review checkout
            </Link>
          )}
        </>
      ) : (
        <div className="py-12 text-center">
          <ShoppingBag size={24} className="mx-auto text-[#c5b7a5]" />
          <p className="mt-3 text-sm text-[#766d62]">Your cart is waiting for a good idea.</p>
        </div>
      )}
    </aside>
  );
}

function BundleCard({ bundle, onAdd }: { bundle: BuyerQueryResponse["bundles"][number]; onAdd: (id: string) => void }) {
  return (
    <div className="rounded-2xl border border-[#d9c7ac] bg-[#fff6e7] p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-[#a17b47]">
            <Sparkles size={12} /> Curated match
          </div>
          <h3 className="mt-2 text-sm font-semibold text-[#211b15]">{bundle.name}</h3>
        </div>
        <span className="whitespace-nowrap text-sm font-semibold text-[#211b15]">{formatCurrency(bundle.total.amount)}</span>
      </div>
      <p className="mt-2 text-xs leading-5 text-[#766d62]">{bundle.reason}</p>
      <button
        onClick={() => bundle.product_ids.forEach(onAdd)}
        className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-[#c7783e] px-3 py-2 text-xs font-medium text-white hover:bg-[#ad6331]"
      >
        Add bundle <ArrowRight size={13} />
      </button>
    </div>
  );
}

export function BuyerPage() {
  const { merchant } = useMerchant();
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<BuyerQueryResponse | null>(null);
  const sessionRef = useMemo(() => {
    const key = "revpilot_buyer_session";
    const existing = sessionStorage.getItem(key);
    if (existing) return existing;
    const created = `buyer_${crypto.randomUUID()}`;
    sessionStorage.setItem(key, created);
    return created;
  }, []);
  const cart = useBuyerCart(merchant?.id, sessionRef);
  const search = useBuyerQuery();
  const cartAction = useBuyerCartAction();

  function ask(text: string) {
    if (!merchant || !text.trim()) return;
    setQuery(text);
    search.mutate({ merchantId: merchant.id, query: text }, { onSuccess: setResult });
  }

  function add(productId: string) {
    if (!merchant) return;
    cartAction.mutate({ merchantId: merchant.id, sessionRef, action: "add", productId, quantity: 1 });
  }

  function mutate(action: "remove" | "clear", productId?: string) {
    if (!merchant) return;
    cartAction.mutate({ merchantId: merchant.id, sessionRef, action, productId });
  }

  if (!merchant) return <div className="text-sm text-[var(--color-text-secondary)]">Loading merchant…</div>;

  return (
    <div className="-m-8 min-h-[calc(100vh-5rem)] bg-[#f7f2e9] px-6 py-8 text-[#211b15] lg:px-10">
      <div className="mx-auto max-w-7xl">
        <div className="flex flex-col justify-between gap-5 md:flex-row md:items-end">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-[#a17b47]">
              <Bot size={15} /> {merchant.name} commerce
            </div>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight md:text-4xl">Shop with AI</h1>
            <p className="mt-2 max-w-xl text-sm leading-6 text-[#766d62]">
              Tell me what you are trying to build. I’ll search the live catalog, check stock, and keep the total inside your budget.
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs text-[#766d62]">
            <span className="h-2 w-2 rounded-full bg-[#5e9d68]" /> Live catalog · explicit checkout consent
          </div>
        </div>

        <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
          <main>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                ask(query);
              }}
              className="rounded-3xl bg-[#211b15] p-5 shadow-[0_16px_40px_rgba(33,27,21,0.2)]"
            >
              <div className="flex items-center gap-2 text-xs text-[#d9c7ac]">
                <Sparkles size={15} className="text-[#e7a85b]" /> What are you shopping for?
              </div>
              <div className="mt-3 flex gap-2">
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="e.g. a gaming setup under ₹5,000"
                  className="min-w-0 flex-1 rounded-xl border border-[#4d4034] bg-[#30271f] px-4 py-3 text-sm text-[#fffaf2] outline-none placeholder:text-[#9e8c78] focus:border-[#e7a85b]"
                />
                <button disabled={search.isPending || !query.trim()} className="rounded-xl bg-[#e7a85b] px-4 py-3 text-sm font-semibold text-[#211b15] disabled:opacity-50">
                  {search.isPending ? "Searching…" : "Find"}
                </button>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {PROMPTS.map((prompt) => (
                  <button type="button" key={prompt} onClick={() => ask(prompt)} className="rounded-full border border-[#4d4034] px-3 py-1.5 text-[11px] text-[#d9c7ac] hover:border-[#e7a85b] hover:text-[#fffaf2]">
                    {prompt}
                  </button>
                ))}
              </div>
            </form>

            {result ? (
              <section className="mt-7">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h2 className="text-lg font-semibold">I found {result.bundles.length ? "a setup that fits" : "some matches"}</h2>
                    <p className="mt-1 text-sm text-[#766d62]">{result.explanation}</p>
                  </div>
                  {result.intent.max_budget && <span className="rounded-full bg-[#eee3d2] px-3 py-1.5 text-xs text-[#766d62]">Budget {formatCurrency(result.intent.max_budget)}</span>}
                </div>
                {result.bundles.length > 0 && (
                  <div className="mt-4 space-y-3">
                    {result.bundles.map((bundle) => <BundleCard key={bundle.id} bundle={bundle} onAdd={add} />)}
                  </div>
                )}
                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                  {result.products.map((product) => <ProductTile key={product.id} product={product} onAdd={add} />)}
                </div>
                {!result.found && <div className="rounded-2xl border border-dashed border-[#d9c7ac] p-10 text-center text-sm text-[#766d62]">No honest catalog match yet. Try another use case or a larger budget.</div>}
              </section>
            ) : (
              <section className="mt-7 rounded-3xl border border-dashed border-[#d9c7ac] px-6 py-16 text-center">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-[#eee3d2]"><Bot size={22} className="text-[#a17b47]" /></div>
                <h2 className="mt-4 font-semibold">A better way to browse</h2>
                <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-[#766d62]">Describe the outcome, not the SKU. Recommendations are grounded in real products, relationships, prices, and stock.</p>
              </section>
            )}
          </main>
          <CartPanel cart={cart.data} onAction={mutate} busy={cartAction.isPending} />
        </div>
      </div>
    </div>
  );
}
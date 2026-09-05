import { useState } from "react";
import { useMerchant } from "../app/MerchantContext";
import { EmptyState, ErrorState } from "../components/EmptyState";
import { useCustomers } from "../services/merchantData";
import { formatCurrency } from "../lib/format";

export function CustomersPage() {
  const { merchant } = useMerchant();
  const [q, setQ] = useState("");
  const customers = useCustomers(merchant?.id, q);
  return (
    <div className="mx-auto max-w-[1440px]">
      <h1 className="text-2xl font-semibold">Customers</h1>
      <p className="mt-1 text-sm text-[var(--color-text-secondary)]">Your highest-value buyers, grounded in paid order history.</p>
      <label className="mt-6 block max-w-md text-xs font-medium text-[var(--color-text-secondary)]">
        Search customers
        <input value={q} onChange={(event) => setQ(event.target.value)} placeholder="Name or email"
          className="mt-2 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text-primary)]" />
      </label>
      <div className="mt-6 overflow-x-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]">
        {customers.isLoading ? <div className="p-8 text-sm text-[var(--color-text-secondary)]">Loading customers…</div>
          : customers.isError ? <ErrorState message="Couldn't load customers." />
          : customers.data?.items.length ? (
            <table className="w-full min-w-[650px] text-left text-sm">
              <caption className="sr-only">Customer value list</caption>
              <thead className="border-b border-[var(--color-border)] text-xs text-[var(--color-text-secondary)]">
                <tr><th className="px-5 py-3 font-medium">Customer</th><th className="px-5 py-3 font-medium">Orders</th><th className="px-5 py-3 font-medium">Lifetime value</th><th className="px-5 py-3 font-medium">Last order</th></tr>
              </thead>
              <tbody>{customers.data.items.map((customer) => <tr key={customer.id} className="border-b border-[var(--color-border)] last:border-0">
                <td className="px-5 py-3"><div className="font-medium">{customer.name}</div><div className="text-xs text-[var(--color-text-secondary)]">{customer.email ?? "No email"}</div></td>
                <td className="px-5 py-3">{customer.order_count}</td><td className="px-5 py-3">{formatCurrency(customer.total_spend)}</td>
                <td className="px-5 py-3 text-xs text-[var(--color-text-secondary)]">{customer.last_order_at ? new Date(customer.last_order_at).toLocaleDateString() : "—"}</td>
              </tr>)}</tbody>
            </table>
          ) : <EmptyState title="No customers found" description="Try a different search or seed the TechNest demo data." />}
      </div>
    </div>
  );
}
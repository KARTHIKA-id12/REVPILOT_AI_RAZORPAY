import { useState } from "react";
import { Search, ShieldCheck, XCircle, Ban, CheckCircle2 } from "lucide-react";
import { useMerchant } from "../app/MerchantContext";
import { useAuditLedger } from "../services/ops";
import { ErrorState } from "../components/EmptyState";

const RESULT_STYLE: Record<string, { icon: typeof CheckCircle2; color: string }> = {
  success: { icon: CheckCircle2, color: "var(--color-success)" },
  failed: { icon: XCircle, color: "var(--color-danger)" },
  blocked: { icon: Ban, color: "var(--color-warning)" },
  recovered: { icon: ShieldCheck, color: "var(--color-info)" },
};

export function AuditLedgerPage() {
  const { merchant } = useMerchant();
  const [result, setResult] = useState("");
  const [search, setSearch] = useState("");
  const { data, isLoading, isError } = useAuditLedger(merchant?.id, result, search);

  if (!merchant) return <div className="text-sm text-[var(--color-text-secondary)]">Loading merchant…</div>;

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Audit Ledger</h1>
          <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
            An append-only view of decisions, guardrails, external actions, and recoveries.
          </p>
        </div>
        <div className="flex gap-2">
          <label className="relative">
            <Search size={14} className="absolute left-3 top-2.5 text-[var(--color-text-secondary)]" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search actions"
              className="w-48 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] py-2 pl-8 pr-3 text-xs outline-none focus:border-[var(--color-accent)]"
            />
          </label>
          <select
            value={result}
            onChange={(event) => setResult(event.target.value)}
            className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-xs"
          >
            <option value="">All outcomes</option>
            <option value="success">Success</option>
            <option value="blocked">Blocked</option>
            <option value="failed">Failed</option>
            <option value="recovered">Recovered</option>
          </select>
        </div>
      </div>

      <div className="mt-6 overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]">
        {isLoading ? <div className="p-6 text-sm text-[var(--color-text-secondary)]">Loading ledger…</div> : null}
        {isError ? <div className="p-6"><ErrorState message="Could not load audit events." /></div> : null}
        {!isLoading && !isError && data?.items.length === 0 ? (
          <div className="p-10 text-center text-sm text-[var(--color-text-secondary)]">No audit events match these filters.</div>
        ) : null}
        <div className="divide-y divide-[var(--color-border)]">
          {data?.items.map((entry) => {
            const style = RESULT_STYLE[entry.result] ?? RESULT_STYLE.success;
            const Icon = style.icon;
            return (
              <div key={entry.id} className="grid gap-3 px-5 py-4 md:grid-cols-[180px_1fr_100px]">
                <div className="font-mono text-[10px] text-[var(--color-text-secondary)]">
                  {entry.created_at ? new Date(entry.created_at).toLocaleString() : "—"}
                  {entry.request_id ? <div className="mt-1 truncate">req {entry.request_id}</div> : null}
                </div>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
                    <span>{entry.action}</span>
                    {entry.tool ? <span className="font-mono text-[10px] text-[var(--color-text-secondary)]">{entry.tool}</span> : null}
                  </div>
                  <div className="mt-1 text-xs text-[var(--color-text-secondary)]">{entry.error ?? entry.reason ?? entry.input_summary ?? "No additional context"}</div>
                  {entry.recovery_action ? <div className="mt-1 text-xs text-[var(--color-info)]">Recovery: {entry.recovery_action}</div> : null}
                </div>
                <div className="flex items-start gap-1.5 text-[10px] font-semibold uppercase" style={{ color: style.color }}>
                  <Icon size={13} /> {entry.result}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <div className="mt-3 text-xs text-[var(--color-text-secondary)]">{data?.total ?? 0} recorded events</div>
    </div>
  );
}
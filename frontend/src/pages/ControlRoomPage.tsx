import { Link } from "react-router-dom";
import { Activity, AlertTriangle, Bell, CheckCircle2, Clock3, ShieldAlert } from "lucide-react";
import { useMerchant } from "../app/MerchantContext";
import { useActionCenter, useAgentTraces, useMarkAllNotificationsRead } from "../services/ops";
import { ErrorState } from "../components/EmptyState";

function CountCard({ label, value, icon: Icon, tone }: { label: string; value: number; icon: typeof Activity; tone: string }) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <Icon size={17} style={{ color: tone }} />
      <div className="mt-4 text-2xl font-semibold">{value}</div>
      <div className="mt-1 text-xs text-[var(--color-text-secondary)]">{label}</div>
    </div>
  );
}

export function ControlRoomPage() {
  const { merchant } = useMerchant();
  const center = useActionCenter(merchant?.id);
  const traces = useAgentTraces(merchant?.id);
  const markAll = useMarkAllNotificationsRead(merchant?.id);

  if (!merchant) return <div className="text-sm text-[var(--color-text-secondary)]">Loading merchant…</div>;
  if (center.isError) return <ErrorState message="Could not load the agent control room." />;
  const counts = center.data?.counts;

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Agent Control Room</h1>
          <p className="mt-1 text-sm text-[var(--color-text-secondary)]">See what the agent proposed, what guardrails stopped, and what needs a merchant decision.</p>
        </div>
        <div className="flex gap-2">
          <Link to="/audit" className="rounded-md border border-[var(--color-border)] px-3 py-2 text-xs hover:border-[var(--color-accent)]">Open audit ledger</Link>
          {counts?.unread_notifications ? (
            <button onClick={() => markAll.mutate()} className="rounded-md bg-[var(--color-accent)] px-3 py-2 text-xs font-semibold text-black">
              Mark notifications read
            </button>
          ) : null}
        </div>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <CountCard label="Pending approvals" value={counts?.pending_approvals ?? 0} icon={Clock3} tone="var(--color-warning)" />
        <CountCard label="Unread notifications" value={counts?.unread_notifications ?? 0} icon={Bell} tone="var(--color-info)" />
        <CountCard label="Failed actions · 24h" value={counts?.failed_actions_24h ?? 0} icon={AlertTriangle} tone="var(--color-danger)" />
        <CountCard label="Blocked actions · 24h" value={counts?.blocked_actions_24h ?? 0} icon={ShieldAlert} tone="var(--color-warning)" />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="flex items-center gap-2 text-sm font-medium"><AlertTriangle size={15} className="text-[var(--color-danger)]" /> Recent failures</h2>
          <div className="mt-4 space-y-3">
            {center.data?.recent_failures.length ? center.data.recent_failures.map((item) => (
              <div key={item.id} className="border-b border-[var(--color-border)] pb-3 last:border-0">
                <div className="flex justify-between gap-3 text-xs font-medium"><span>{item.action}</span><span className="uppercase text-[var(--color-danger)]">{item.result}</span></div>
                <div className="mt-1 text-xs text-[var(--color-text-secondary)]">{item.error ?? item.reason ?? "No failure detail recorded."}</div>
              </div>
            )) : <div className="text-xs text-[var(--color-text-secondary)]">No failed or blocked actions recorded.</div>}
          </div>
        </section>

        <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="flex items-center gap-2 text-sm font-medium"><Bell size={15} className="text-[var(--color-info)]" /> Notifications</h2>
          <div className="mt-4 space-y-3">
            {center.data?.notifications.length ? center.data.notifications.map((item) => (
              <div key={item.id} className="border-b border-[var(--color-border)] pb-3 last:border-0">
                <div className="text-xs font-medium">{item.title}</div>
                <div className="mt-1 text-xs text-[var(--color-text-secondary)]">{item.body}</div>
              </div>
            )) : <div className="text-xs text-[var(--color-text-secondary)]">You're all caught up.</div>}
          </div>
        </section>
      </div>

      <section className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <h2 className="flex items-center gap-2 text-sm font-medium"><Activity size={15} className="text-[var(--color-success)]" /> Agent traces</h2>
        <div className="mt-4 overflow-x-auto">
          {traces.isLoading ? <div className="text-xs text-[var(--color-text-secondary)]">Loading traces…</div> : null}
          <table className="w-full min-w-[560px] text-left text-xs">
            <thead className="text-[10px] uppercase tracking-wide text-[var(--color-text-secondary)]">
              <tr><th className="pb-3">Started</th><th className="pb-3">Channel</th><th className="pb-3">Messages</th><th className="pb-3">Tools</th><th className="pb-3">Actions</th><th className="pb-3">Status</th></tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {traces.data?.items.map((trace) => (
                <tr key={trace.id}>
                  <td className="py-3 font-mono text-[10px] text-[var(--color-text-secondary)]">{trace.started_at ? new Date(trace.started_at).toLocaleString() : "—"}</td>
                  <td className="py-3">{trace.channel}</td><td className="py-3">{trace.message_count}</td><td className="py-3">{trace.tool_call_count}</td><td className="py-3">{trace.action_count}</td>
                  <td className="py-3"><span className="inline-flex items-center gap-1 uppercase text-[10px]"><CheckCircle2 size={12} className="text-[var(--color-success)]" />{trace.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!traces.isLoading && !traces.data?.items.length ? <div className="pt-2 text-xs text-[var(--color-text-secondary)]">No agent sessions yet.</div> : null}
        </div>
      </section>
    </div>
  );
}
import { useHealth } from "../services/health";

export function SystemStatusBadge() {
  const { data, isLoading, isError } = useHealth();

  if (isLoading) {
    return <span className="text-xs text-[var(--color-text-secondary)]">Checking system status…</span>;
  }

  if (isError || !data) {
    return (
      <span className="flex items-center gap-2 text-xs text-[var(--color-danger)]">
        <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-danger)]" /> Backend unreachable
      </span>
    );
  }

  const healthy = data.status === "healthy";
  const color = healthy ? "var(--color-success)" : "var(--color-warning)";

  return (
    <div className="flex items-center gap-4 text-xs text-[var(--color-text-secondary)]">
      <span className="flex items-center gap-2">
        <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
        {healthy ? "All systems operational" : "Degraded"}
      </span>
      <span className="font-mono">db: {data.database}</span>
      <span className="font-mono">ai: {data.ai}</span>
      <span className="font-mono">payments: {data.payment_provider}</span>
    </div>
  );
}

interface MetricCardProps {
  label: string;
  value: string;
  sublabel?: string;
  tone?: "neutral" | "positive" | "negative" | "warning";
}

const TONE_COLORS: Record<NonNullable<MetricCardProps["tone"]>, string> = {
  neutral: "var(--color-text-primary)",
  positive: "var(--color-success)",
  negative: "var(--color-danger)",
  warning: "var(--color-warning)",
};

export function MetricCard({ label, value, sublabel, tone = "neutral" }: MetricCardProps) {
  return (
    <div className="card-hover rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <div className="text-xs uppercase tracking-wide text-[var(--color-text-secondary)]">{label}</div>
      <div className="mt-2 text-2xl font-semibold" style={{ color: TONE_COLORS[tone] }}>
        {value}
      </div>
      {sublabel && <div className="mt-1 text-xs text-[var(--color-text-secondary)]">{sublabel}</div>}
    </div>
  );
}

export function MetricCardSkeleton() {
  return (
    <div aria-hidden="true" className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <div className="h-3 w-20 animate-pulse rounded bg-[var(--color-border)]" />
      <div className="mt-3 h-7 w-28 animate-pulse rounded bg-[var(--color-border)]" />
    </div>
  );
}

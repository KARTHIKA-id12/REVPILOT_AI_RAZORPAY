import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { RevenueTrendPoint } from "../types/api";
import { formatCompactNumber, formatCurrency } from "../lib/format";

export function RevenueTrendChart({ points }: { points: RevenueTrendPoint[] }) {
  if (points.length === 0) return null;

  return (
    <div role="img" aria-label="Revenue trend chart">
      <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="revenueFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-accent)" stopOpacity={0.35} />
            <stop offset="100%" stopColor="var(--color-accent)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis
          dataKey="period"
          tick={{ fill: "var(--color-text-secondary)", fontSize: 11 }}
          axisLine={{ stroke: "var(--color-border)" }}
          tickLine={false}
        />
        <YAxis
          tickFormatter={(v) => formatCompactNumber(v)}
          tick={{ fill: "var(--color-text-secondary)", fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          width={48}
        />
        <Tooltip
          formatter={(value) => [formatCurrency(Number(value ?? 0)), "Revenue"]}
          contentStyle={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 8, fontSize: 12 }}
          labelStyle={{ color: "var(--color-text-secondary)" }}
        />
        <Area type="monotone" dataKey="revenue" stroke="var(--color-accent)" strokeWidth={2} fill="url(#revenueFill)" />
      </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

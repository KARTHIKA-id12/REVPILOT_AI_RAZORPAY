import { AlertTriangle, CheckCircle2, ShieldAlert, TriangleAlert } from "lucide-react";
import type { RiskLevel } from "../types/api";

const RISK_CONFIG: Record<RiskLevel, { label: string; color: string; icon: typeof CheckCircle2 }> = {
  low: { label: "Low risk", color: "var(--color-success)", icon: CheckCircle2 },
  medium: { label: "Medium risk", color: "var(--color-warning)", icon: TriangleAlert },
  high: { label: "High risk", color: "var(--color-danger)", icon: AlertTriangle },
  critical: { label: "Critical risk", color: "var(--color-danger)", icon: ShieldAlert },
};

export function RiskBadge({ level }: { level: RiskLevel }) {
  const config = RISK_CONFIG[level];
  const Icon = config.icon;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium" style={{ color: config.color }}>
      <Icon size={13} strokeWidth={2.25} />
      {config.label}
    </span>
  );
}

const TYPE_LABELS: Record<string, string> = {
  cross_sell: "Cross-sell",
  bundle: "Bundle",
  abandoned_cart: "Abandoned cart",
  reactivation: "Reactivation",
  repeat_purchase: "Repeat purchase",
};

export function OpportunityTypeBadge({ type }: { type: string }) {
  return (
    <span className="rounded-full border border-[var(--color-border)] px-2 py-0.5 text-[10px] uppercase tracking-wide text-[var(--color-text-secondary)]">
      {TYPE_LABELS[type] ?? type}
    </span>
  );
}

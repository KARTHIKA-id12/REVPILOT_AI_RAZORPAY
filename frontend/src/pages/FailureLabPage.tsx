import { CheckCircle2, AlertTriangle, XCircle, Info, ShieldAlert } from "lucide-react";
import { useMerchant } from "../app/MerchantContext";
import { useFailureScenarios, useTriggerFailure } from "../services/failureLab";
import { ErrorState } from "../components/EmptyState";
import type { FailureTraceStep } from "../types/api";

const STATUS_CONFIG: Record<FailureTraceStep["status"], { icon: typeof CheckCircle2; color: string }> = {
  ok: { icon: CheckCircle2, color: "var(--color-success)" },
  info: { icon: Info, color: "var(--color-info)" },
  warning: { icon: AlertTriangle, color: "var(--color-warning)" },
  blocked: { icon: ShieldAlert, color: "var(--color-warning)" },
  failure: { icon: XCircle, color: "var(--color-danger)" },
};

function TraceStepRow({ step }: { step: FailureTraceStep }) {
  const config = STATUS_CONFIG[step.status];
  const Icon = config.icon;
  return (
    <div className="flex items-start gap-3 border-b border-[var(--color-border)] py-3 last:border-0">
      <Icon size={16} style={{ color: config.color }} className="mt-0.5 shrink-0" />
      <div className="min-w-0">
        <div className="font-mono text-xs font-semibold uppercase tracking-wide" style={{ color: config.color }}>
          {step.stage}
        </div>
        <div className="mt-0.5 text-sm text-[var(--color-text-secondary)]">{step.detail}</div>
      </div>
    </div>
  );
}

export function FailureLabPage() {
  const { merchant } = useMerchant();
  const { data: scenarios, isLoading: scenariosLoading } = useFailureScenarios();
  const trigger = useTriggerFailure(merchant?.id);

  if (!merchant) {
    return <div className="text-sm text-[var(--color-text-secondary)]">Loading merchant…</div>;
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold">Failure Lab</h1>
      <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
        Every scenario below drives the real production code path — the same policy engine, permission engine, and
        payment pipeline used everywhere else in RevPilot. Nothing here is a scripted response.
      </p>

      <div className="mt-6 flex flex-wrap gap-2">
        {scenariosLoading ? (
          <div className="text-xs text-[var(--color-text-secondary)]">Loading scenarios…</div>
        ) : (
          scenarios?.scenarios.map((s) => (
            <div key={s.code} className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3 sm:w-auto sm:max-w-xs">
              <button
                onClick={() => trigger.mutate(s.code)}
                disabled={trigger.isPending}
                className="text-left text-xs font-medium text-[var(--color-text-primary)] hover:text-[var(--color-accent)] disabled:opacity-50"
              >
                {s.label}
              </button>
              {s.description && <div className="mt-1 text-[10px] leading-4 text-[var(--color-text-secondary)]">{s.description}</div>}
            </div>
          ))
        )}
      </div>

      <div className="mt-8 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 font-mono">
        {trigger.isPending ? (
          <div className="text-sm text-[var(--color-text-secondary)]">Running scenario against real backend state…</div>
        ) : trigger.isError ? (
          <ErrorState message="Scenario failed to run." />
        ) : trigger.data ? (
          <div>
            {trigger.data.label && <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-accent)]">{trigger.data.label}</div>}
            {trigger.data.trace.map((step, i) => (
              <TraceStepRow key={i} step={step} />
            ))}
            {trigger.data.final_campaign_status && (
              <div className="mt-4 rounded-lg border border-[var(--color-success)]/30 bg-[var(--color-success)]/5 px-4 py-3 text-sm text-[var(--color-success)]">
                Final campaign status: <span className="font-semibold">{trigger.data.final_campaign_status}</span>
              </div>
            )}
          </div>
        ) : (
          <p className="text-sm text-[var(--color-text-secondary)]">
            Select a scenario above to see it detected, contained, and recovered from — live, against a real demo
            campaign.
          </p>
        )}
      </div>
    </div>
  );
}

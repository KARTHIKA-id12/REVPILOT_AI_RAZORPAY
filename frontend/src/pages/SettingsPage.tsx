import { useState } from "react";
import { AlertOctagon } from "lucide-react";
import { useMerchant } from "../app/MerchantContext";
import {
  useEmergencyStop, usePermissions, usePolicies, useSetEmergencyStop, useUpdatePermission, useUpdatePolicy,
} from "../services/settings";
import type { PermissionMode, PolicyItem } from "../types/api";

const MODE_STYLES: Record<PermissionMode, string> = {
  ALLOW: "text-[var(--color-success)] border-[var(--color-success)]/40",
  APPROVAL: "text-[var(--color-warning)] border-[var(--color-warning)]/40",
  DENY: "text-[var(--color-danger)] border-[var(--color-danger)]/40",
};

function EmergencyStopPanel() {
  const { merchant } = useMerchant();
  const { data } = useEmergencyStop(merchant?.id);
  const setStop = useSetEmergencyStop(merchant?.id);
  const enabled = data?.enabled ?? false;

  return (
    <div
      className={`rounded-xl border p-5 ${enabled ? "border-[var(--color-danger)] bg-[var(--color-danger)]/5" : "border-[var(--color-border)] bg-[var(--color-surface)]"}`}
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-start gap-3">
          <AlertOctagon size={20} className={enabled ? "text-[var(--color-danger)]" : "text-[var(--color-text-secondary)]"} />
          <div>
            <h3 className="text-sm font-medium">Emergency Stop</h3>
            <p className="mt-1 text-xs text-[var(--color-text-secondary)]">
              {enabled
                ? "All financial agent actions are blocked. Read-only analysis and simulation remain available."
                : "Instantly blocks every financial action (discounts, payment links, orders) regardless of individual permission settings. Analytics and simulation stay available."}
            </p>
          </div>
        </div>
        <button
          onClick={() => setStop.mutate(!enabled)}
          disabled={setStop.isPending}
          className={`shrink-0 rounded-md px-4 py-2 text-xs font-semibold ${
            enabled
              ? "bg-[var(--color-surface)] text-[var(--color-text-primary)] border border-[var(--color-border)]"
              : "bg-[var(--color-danger)] text-white"
          } disabled:opacity-50`}
        >
          {enabled ? "Resume normal operation" : "Activate Emergency Stop"}
        </button>
      </div>
    </div>
  );
}

function PermissionsPanel() {
  const { merchant } = useMerchant();
  const { data, isLoading } = usePermissions(merchant?.id);
  const updatePermission = useUpdatePermission(merchant?.id);

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <h3 className="text-sm font-medium">Agent Permissions</h3>
      <p className="mt-1 text-xs text-[var(--color-text-secondary)]">
        Controls what the AI Growth Agent can do without asking. ALLOW runs freely, APPROVAL requires your sign-off
        in the Approval Center, DENY blocks the action outright.
      </p>

      <div className="mt-4 divide-y divide-[var(--color-border)]">
        {isLoading ? (
          <div className="py-6 text-center text-xs text-[var(--color-text-secondary)]">Loading…</div>
        ) : (
          data?.items.map((item) => (
            <div key={item.action_code} className="flex items-center justify-between gap-4 py-3">
              <div>
                <div className="text-sm font-mono text-[var(--color-text-primary)]">{item.action_code}</div>
                <div className="text-xs text-[var(--color-text-secondary)]">{item.description}</div>
              </div>
              <div className="flex shrink-0 gap-1.5">
                {(["ALLOW", "APPROVAL", "DENY"] as PermissionMode[]).map((mode) => (
                  <button
                    key={mode}
                    onClick={() => updatePermission.mutate({ actionCode: item.action_code, mode })}
                    disabled={updatePermission.isPending}
                    className={`rounded-md border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide disabled:opacity-50 ${
                      item.mode === mode ? MODE_STYLES[mode] : "border-[var(--color-border)] text-[var(--color-text-secondary)]"
                    }`}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function PolicyRow({ item }: { item: PolicyItem }) {
  const { merchant } = useMerchant();
  const updatePolicy = useUpdatePolicy(merchant?.id);
  const [localValue, setLocalValue] = useState<string>(String(item.value));

  if (item.type === "boolean") {
    return (
      <div className="flex items-center justify-between py-3">
        <div>
          <div className="text-sm text-[var(--color-text-primary)]">{item.label}</div>
          <div className="font-mono text-[10px] text-[var(--color-text-secondary)]">{item.code}</div>
        </div>
        <button
          onClick={() => updatePolicy.mutate({ code: item.code, value: !item.value })}
          disabled={updatePolicy.isPending}
          className={`h-6 w-11 shrink-0 rounded-full transition-colors ${item.value ? "bg-[var(--color-accent)]" : "bg-[var(--color-border)]"} disabled:opacity-50`}
        >
          <span className={`block h-5 w-5 translate-y-0.5 rounded-full bg-white transition-transform ${item.value ? "translate-x-5" : "translate-x-0.5"}`} />
        </button>
      </div>
    );
  }

  const suffix = item.type === "percent" ? "%" : item.type === "amount" ? "₹" : "";

  return (
    <div className="flex items-center justify-between py-3">
      <div>
        <div className="text-sm text-[var(--color-text-primary)]">{item.label}</div>
        <div className="font-mono text-[10px] text-[var(--color-text-secondary)]">{item.code}</div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <span className="text-xs text-[var(--color-text-secondary)]">{suffix}</span>
        <input
          type="number"
          value={localValue}
          min={item.min ?? undefined}
          max={item.max ?? undefined}
          onChange={(e) => setLocalValue(e.target.value)}
          onBlur={() => {
            const num = Number(localValue);
            if (!Number.isNaN(num)) updatePolicy.mutate({ code: item.code, value: num });
          }}
          className="w-28 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-sm text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent)]"
        />
      </div>
    </div>
  );
}

function PoliciesPanel() {
  const { merchant } = useMerchant();
  const { data, isLoading } = usePolicies(merchant?.id);

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <h3 className="text-sm font-medium">Policy Guardrails</h3>
      <p className="mt-1 text-xs text-[var(--color-text-secondary)]">
        Deterministic limits the agent can never exceed, regardless of what it argues for. Checked in code, not by
        the model.
      </p>

      <div className="mt-4 divide-y divide-[var(--color-border)]">
        {isLoading ? (
          <div className="py-6 text-center text-xs text-[var(--color-text-secondary)]">Loading…</div>
        ) : (
          data?.items.map((item) => <PolicyRow key={item.code} item={item} />)
        )}
      </div>
    </div>
  );
}

export function SettingsPage() {
  const { merchant } = useMerchant();

  if (!merchant) {
    return <div className="text-sm text-[var(--color-text-secondary)]">Loading merchant…</div>;
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold">Settings</h1>
      <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
        Agent guardrails for {merchant.name}. Changes take effect immediately on the next agent action.
      </p>

      <div className="mt-6 space-y-6">
        <EmergencyStopPanel />
        <PermissionsPanel />
        <PoliciesPanel />
      </div>
    </div>
  );
}

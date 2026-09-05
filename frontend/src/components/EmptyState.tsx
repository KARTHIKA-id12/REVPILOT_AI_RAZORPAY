import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  description: string;
  action?: ReactNode;
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div role="status" className="rounded-xl border border-dashed border-[var(--color-border)] px-6 py-12 text-center">
      <h3 className="text-sm font-medium text-[var(--color-text-primary)]">{title}</h3>
      <p className="mx-auto mt-1.5 max-w-sm text-xs text-[var(--color-text-secondary)]">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div role="alert" className="rounded-xl border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/5 px-6 py-8 text-center">
      <p className="text-sm text-[var(--color-danger)]">{message}</p>
    </div>
  );
}

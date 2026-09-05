export function ComingSoonPage({ title, phase }: { title: string; phase: string }) {
  return (
    <div>
      <h1 className="text-2xl font-semibold">{title}</h1>
      <div className="mt-6 rounded-xl border border-dashed border-[var(--color-border)] px-6 py-12 text-center">
        <p className="text-sm text-[var(--color-text-primary)]">Not built yet.</p>
        <p className="mt-1.5 text-xs text-[var(--color-text-secondary)]">
          This screen is planned for <span className="font-mono">{phase}</span> of the build roadmap — see{" "}
          <span className="font-mono">docs/roadmap-testing-deployment.md</span>. It's intentionally not a dead link:
          the route loads and tells you exactly where it stands.
        </p>
      </div>
    </div>
  );
}

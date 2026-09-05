import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { UploadCloud, CheckCircle2, AlertTriangle, FileText, Bot } from "lucide-react";
import { useMerchant } from "../app/MerchantContext";
import { useUploadCustomers, useUploadOrders, useUploadSchema } from "../services/dataImport";
import { ErrorState } from "../components/EmptyState";
import type { CustomersUploadResult, OrdersUploadResult } from "../services/dataImport";

function UploadCard({
  title, description, accept, onUpload, isPending, error, result,
}: {
  title: string;
  description: string;
  accept: string[];
  onUpload: (file: File) => void;
  isPending: boolean;
  error: unknown;
  result: CustomersUploadResult | OrdersUploadResult | undefined;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <div className="flex items-start gap-3">
        <UploadCloud size={20} className="mt-0.5 shrink-0 text-[var(--color-text-secondary)]" />
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-medium text-[var(--color-text-primary)]">{title}</h3>
          <p className="mt-1 text-xs text-[var(--color-text-secondary)]">{description}</p>

          <div className="mt-3 mb-2 rounded-md border border-dashed border-[var(--color-border)] p-3">
            <p className="mb-2 text-[11px] uppercase tracking-wide text-[var(--color-text-secondary)]">Required / optional columns</p>
            <ul className="space-y-0.5 text-xs text-[var(--color-text-primary)]">
              {accept.map((col) => (
                <li key={col} className="font-mono">{col}</li>
              ))}
            </ul>
          </div>

          <input
            ref={inputRef}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) {
                setFileName(file.name);
                onUpload(file);
              }
            }}
          />
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={isPending}
            className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-[var(--color-text-primary)] hover:bg-[var(--color-bg)] disabled:opacity-50"
          >
            {isPending ? "Uploading & analyzing…" : "Choose CSV file"}
          </button>
          {fileName && !isPending && <span className="ml-2 text-xs text-[var(--color-text-secondary)]">{fileName}</span>}

          {error != null && (
            <div className="mt-3">
              <ErrorState message={error instanceof Error ? error.message : "Upload failed."} />
            </div>
          )}

          {result && (
            <div className="mt-3 space-y-2 rounded-md border border-[var(--color-success)]/30 bg-[var(--color-success)]/5 p-3 text-xs">
              <div className="flex items-center gap-1.5 font-medium text-[var(--color-success)]">
                <CheckCircle2 size={14} />
                Import complete
              </div>
              {"customers_created" in result ? (
                <p className="text-[var(--color-text-primary)]">
                  {result.customers_created} customer(s) created, {result.customers_matched_existing} already existed and were matched by email.
                </p>
              ) : (
                <>
                  <p className="text-[var(--color-text-primary)]">{result.orders_created} order(s) imported.</p>
                  <p className="text-[var(--color-text-secondary)]">
                    Analytics recomputed on the combined dataset —{" "}
                    <strong className="text-[var(--color-text-primary)]">{result.analytics_refreshed.opportunities_detected}</strong> open
                    opportunities detected ({Object.entries(result.analytics_refreshed.opportunities_by_type).map(([k, v]) => `${v} ${k.replace("_", "-")}`).join(", ")}).
                  </p>
                </>
              )}
              {result.rows_skipped.length > 0 && (
                <div className="mt-2 border-t border-[var(--color-border)] pt-2">
                  <p className="mb-1 flex items-center gap-1.5 font-medium text-[var(--color-warning)]">
                    <AlertTriangle size={13} />
                    {result.rows_skipped.length} row(s) skipped
                  </p>
                  <ul className="max-h-32 space-y-0.5 overflow-y-auto font-mono text-[11px] text-[var(--color-text-secondary)]">
                    {result.rows_skipped.map((r) => (
                      <li key={r.row}>row {r.row}: {r.reason}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function DataUploadPage() {
  const { merchant } = useMerchant();
  const { data: schema } = useUploadSchema();
  const uploadCustomers = useUploadCustomers(merchant?.id);
  const uploadOrders = useUploadOrders(merchant?.id);

  const bothUploaded = Boolean(uploadCustomers.data && uploadOrders.data);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-[var(--color-text-primary)]">Manage Data</h1>
        <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
          Upload your real customer and order history, or view the existing data.
        </p>
        <div className="mt-4 flex gap-3">
          <a href="/customers" className="rounded border border-[var(--color-border)] px-3 py-1.5 text-xs hover:border-[var(--color-accent)]">View Customers</a>
          <a href="/products" className="rounded border border-[var(--color-border)] px-3 py-1.5 text-xs hover:border-[var(--color-accent)]">View Products</a>
          <a href="/technest_dataset.csv" download="technest_dataset.csv" className="rounded bg-[var(--color-accent)] text-[#1a1200] px-3 py-1.5 text-xs font-medium hover:opacity-90">
            Download TechNest Dataset
          </a>
        </div>
      </div>

      <div className="flex items-start gap-2 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-xs text-[var(--color-text-secondary)]">
        <FileText size={14} className="mt-0.5 shrink-0" />
        <p>
          Upload <strong className="text-[var(--color-text-primary)]">customers.csv</strong> first if your
          orders reference customers by email that don't already exist — the orders importer will also
          auto-create a minimal customer record for any new email it sees.
        </p>
      </div>

      <UploadCard
        title="Customers CSV"
        description="Adds or matches customer records by email. Existing customers are matched, not duplicated."
        accept={schema?.customers_csv.required_or_optional_columns ?? ["name (required)", "email", "phone", "external_ref"]}
        onUpload={(file) => uploadCustomers.mutate(file)}
        isPending={uploadCustomers.isPending}
        error={uploadCustomers.error}
        result={uploadCustomers.data}
      />

      <UploadCard
        title="Orders CSV"
        description="One row per order. product_skus must match SKUs already in your catalog to appear in line-item breakdowns — unmatched SKUs still count toward the order total."
        accept={schema?.orders_csv.required_or_optional_columns ?? [
          "customer_email (required)", "total_amount (required)", "status (required)", "created_at (required)", "product_skus (optional)",
        ]}
        onUpload={(file) => uploadOrders.mutate(file)}
        isPending={uploadOrders.isPending}
        error={uploadOrders.error}
        result={uploadOrders.data}
      />

      {bothUploaded && (
        <div className="rounded-xl border border-[var(--color-accent)] bg-[var(--color-surface)] p-5 shadow-lg flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-sm text-[var(--color-text-primary)]">Data Import Complete!</h3>
            <p className="text-xs text-[var(--color-text-secondary)] mt-1">Both Customer and Order datasets have been successfully imported and analytics recomputed.</p>
          </div>
          <Link
            to="/agent"
            className="inline-flex items-center gap-2 rounded-md bg-[var(--color-accent)] text-[#1a1200] px-4 py-2 text-xs font-bold shadow hover:opacity-90 transition-opacity shrink-0"
          >
            <Bot size={18} /> Get Analysis with AI Agent &rarr;
          </Link>
        </div>
      )}
    </div>
  );
}

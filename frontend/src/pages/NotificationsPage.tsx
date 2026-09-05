import { Bell, CheckCircle2, ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { useMerchant } from "../app/MerchantContext";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";

export function NotificationsPage() {
  const { merchant } = useMerchant();
  
  // Use audit ledger as a proxy for notifications
  const { data } = useQuery({
    queryKey: ["notifications", merchant?.id],
    queryFn: () => apiFetch<any>(`/api/v1/audit?merchant_id=${merchant?.id}&page_size=20`),
    enabled: !!merchant?.id,
  });

  const notifications = (data?.items || []).filter((item: any) => 
    ["CREATE_CAMPAIGN_DRAFT", "CREATE_DISCOUNT", "CREATE_PAYMENT_LINK"].includes(item.action)
  );

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold flex items-center gap-2">
          <Bell className="text-[var(--color-accent)]" /> Notifications
        </h1>
        <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
          Real-time alerts and autonomous agent activities.
        </p>
      </div>

      <div className="space-y-3">
        {notifications.length === 0 && (
          <div className="p-8 text-center text-sm text-[var(--color-text-secondary)] bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)]">
            No recent notifications.
          </div>
        )}
        {notifications.map((n: any, idx: number) => (
          <div key={idx} className="flex gap-4 p-4 bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] shadow-sm">
             <div className="mt-1">
               {n.result === "success" ? <CheckCircle2 className="text-green-500" size={20} /> : <ShieldAlert className="text-[var(--color-warning)]" size={20} />}
             </div>
             <div>
                <h3 className="font-semibold text-sm">
                  {n.action === "CREATE_CAMPAIGN_DRAFT" && "Campaign Draft Created"}
                  {n.action === "CREATE_DISCOUNT" && "Approval Required: New Campaign"}
                  {n.action === "CREATE_PAYMENT_LINK" && "Payment Link Executed"}
                </h3>
                <p className="text-xs text-[var(--color-text-secondary)] mt-1">{n.input_summary} — {n.reason}</p>
                <div className="text-[10px] text-[var(--color-text-secondary)] mt-2">{new Date(n.timestamp).toLocaleString()}</div>
                
                {n.action === "CREATE_DISCOUNT" && n.result === "blocked" && (
                   <Link to="/approvals" className="mt-3 inline-block bg-[var(--color-accent)] text-[#1a1200] px-3 py-1.5 rounded text-xs font-bold shadow hover:opacity-90">
                     Review in Approval Center
                   </Link>
                )}
             </div>
          </div>
        ))}
      </div>
    </div>
  );
}

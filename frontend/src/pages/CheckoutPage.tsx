import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, CheckCircle2, LockKeyhole, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { useMerchant } from "../app/MerchantContext";
import { formatCurrency } from "../lib/format";
import { useCheckoutConfirm, useCheckoutPreview, useCheckoutVerify } from "../services/buyer";
import type { CheckoutPreview, CheckoutResult } from "../types/api";

export function CheckoutPage() {
  const { merchant } = useMerchant();
  const [preview, setPreview] = useState<CheckoutPreview | null>(null);
  const [result, setResult] = useState<CheckoutResult | null>(null);
  const [buyerName, setBuyerName] = useState("");
  const [buyerEmail, setBuyerEmail] = useState("");
  const sessionRef = useMemo(() => sessionStorage.getItem("revpilot_buyer_session") ?? "", []);
  const loadPreview = useCheckoutPreview();
  const confirm = useCheckoutConfirm();
  const verify = useCheckoutVerify();

  useEffect(() => {
    if (merchant?.id && sessionRef && !loadPreview.isPending) {
      loadPreview.mutate({ merchantId: merchant.id, sessionRef }, { onSuccess: setPreview });
    }
    // This page intentionally loads one fresh server preview on entry.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [merchant?.id, sessionRef]);

  if (!merchant) return <div className="text-sm text-[var(--color-text-secondary)]">Loading merchant…</div>;

  if (result?.order_status === "paid") {
    return (
      <div className="-m-8 flex min-h-[calc(100vh-5rem)] items-center justify-center bg-[#f7f2e9] px-6 text-[#211b15]">
        <div className="max-w-md rounded-3xl border border-[#d9c7ac] bg-[#fffaf2] p-8 text-center shadow-[0_16px_40px_rgba(75,56,28,0.1)]">
          <CheckCircle2 size={44} className="mx-auto text-[#5e9d68]" />
          <h1 className="mt-5 text-2xl font-semibold">Order confirmed</h1>
          <p className="mt-2 text-sm leading-6 text-[#766d62]">Payment verified and your order is now recorded in {merchant.name}’s commerce ledger.</p>
          <div className="mt-5 rounded-2xl bg-[#f1e9dc] p-4 text-left text-sm">
            <div className="flex justify-between"><span className="text-[#766d62]">Order</span><span className="font-mono text-xs">{result.order_id.slice(0, 12)}…</span></div>
            <div className="mt-2 flex justify-between"><span className="text-[#766d62]">Paid</span><span className="font-semibold">{formatCurrency(result.amount.amount)}</span></div>
          </div>
          <Link to="/shop" className="mt-6 inline-flex rounded-full bg-[#211b15] px-4 py-2.5 text-sm font-medium text-[#fffaf2]">Continue shopping</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="-m-8 min-h-[calc(100vh-5rem)] bg-[#f7f2e9] px-6 py-8 text-[#211b15] lg:px-10">
      <div className="mx-auto max-w-4xl">
        <Link to="/shop" className="inline-flex items-center gap-1.5 text-xs text-[#766d62] hover:text-[#211b15]"><ArrowLeft size={14} /> Back to Shop with AI</Link>
        <div className="mt-6 flex items-end justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.2em] text-[#a17b47]">Secure checkout</div>
            <h1 className="mt-2 text-3xl font-semibold">Review your order</h1>
          </div>
          <div className="hidden items-center gap-1.5 text-xs text-[#766d62] sm:flex"><LockKeyhole size={14} /> Prices rechecked live</div>
        </div>

        {loadPreview.isPending && <div className="mt-8 rounded-3xl bg-[#fffaf2] p-8 text-sm text-[#766d62]">Refreshing your cart and checking availability…</div>}
        {loadPreview.isError && <div className="mt-8 rounded-3xl border border-[#c7783e]/30 bg-[#fff6e7] p-8 text-sm text-[#766d62]">Your cart could not be prepared. Return to the shop and try again.</div>}
        {preview && (
          <div className="mt-8 grid gap-6 md:grid-cols-[1fr_300px]">
            <section className="rounded-3xl border border-[#e5ded2] bg-[#fffaf2] p-6">
              <h2 className="font-semibold">Products</h2>
              <div className="mt-5 divide-y divide-[#eee6da]">
                {preview.items.map((item) => (
                  <div key={item.id} className="flex items-center justify-between gap-4 py-4 first:pt-0 last:pb-0">
                    <div><div className="text-sm font-medium">{item.name}</div><div className="mt-1 text-xs text-[#766d62]">Quantity {item.quantity} · {formatCurrency(item.unit_price.amount)} each</div></div>
                    <span className="text-sm font-semibold">{formatCurrency(item.line_total.amount)}</span>
                  </div>
                ))}
              </div>
              <div className="mt-6 border-t border-[#e5ded2] pt-5">
                <div className="flex justify-between text-sm"><span className="text-[#766d62]">Subtotal</span><span>{formatCurrency(preview.subtotal.amount)}</span></div>
                <div className="mt-2 flex justify-between text-sm"><span className="text-[#766d62]">Shipping</span><span>Free</span></div>
                <div className="mt-4 flex justify-between text-lg font-semibold"><span>Total</span><span>{formatCurrency(preview.total.amount)}</span></div>
              </div>
            </section>
            <section className="rounded-3xl border border-[#d9c7ac] bg-[#fff6e7] p-6">
              <h2 className="font-semibold">Your details</h2>
              <p className="mt-2 text-xs leading-5 text-[#766d62]">We use these details to attach the payment to your order. No purchase happens until you confirm below.</p>
              <label className="mt-5 block text-xs font-medium">Name<input value={buyerName} onChange={(event) => setBuyerName(event.target.value)} className="mt-2 w-full rounded-xl border border-[#dfd0ba] bg-[#fffaf2] px-3 py-2.5 text-sm outline-none focus:border-[#c7783e]" placeholder="Your name" /></label>
              <label className="mt-3 block text-xs font-medium">Email<input value={buyerEmail} onChange={(event) => setBuyerEmail(event.target.value)} type="email" className="mt-2 w-full rounded-xl border border-[#dfd0ba] bg-[#fffaf2] px-3 py-2.5 text-sm outline-none focus:border-[#c7783e]" placeholder="you@example.com" /></label>
              <div className="mt-5 flex items-start gap-2 text-[11px] leading-4 text-[#766d62]"><ShieldCheck size={15} className="mt-0.5 shrink-0 text-[#5e9d68]" /> The server will recalculate every line and the final amount before creating the {preview.payment_provider === "mock" ? "demo payment" : "Razorpay payment"}.</div>
              <button
                onClick={() => confirm.mutate({ merchantId: merchant.id, sessionRef, previewId: preview.preview_id, buyerName, buyerEmail }, { onSuccess: setResult })}
                disabled={confirm.isPending || buyerName.trim().length < 2 || !buyerEmail.includes("@")}
                className="mt-6 w-full rounded-xl bg-[#211b15] px-4 py-3 text-sm font-semibold text-[#fffaf2] disabled:opacity-40"
              >
                {confirm.isPending ? "Preparing payment…" : `Confirm order · ${formatCurrency(preview.total.amount)}`}
              </button>
              {confirm.isError && <p className="mt-3 text-xs text-[#b24c3f]">The cart changed or payment preparation failed. Refresh this page and review again.</p>}
            </section>
          </div>
        )}
        {result && result.order_status === "pending" && (
          <section className="mt-6 rounded-3xl border border-[#d9c7ac] bg-[#fff6e7] p-6">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#a17b47]">Order ready</div>
            <h2 className="mt-2 text-xl font-semibold">Confirm payment</h2>
            <p className="mt-2 text-sm leading-6 text-[#766d62]">Your order is created as pending. {result.demo_payment_available ? "This is Demo Payment Mode, so you can complete the verified demo payment below." : "Complete the Razorpay checkout, then return with its verified payment signature."}</p>
            {result.demo_payment_available && (
              <button onClick={() => verify.mutate({ merchantId: merchant.id, orderId: result.order_id }, { onSuccess: setResult })} disabled={verify.isPending} className="mt-5 rounded-xl bg-[#c7783e] px-4 py-3 text-sm font-semibold text-white disabled:opacity-50">
                {verify.isPending ? "Verifying demo payment…" : "Complete demo payment"}
              </button>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
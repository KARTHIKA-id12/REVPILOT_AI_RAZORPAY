# RevPilot AI — Product & Architecture Decisions

## Why modular monolith?
Fast development, clear domain boundaries, no premature distributed-systems
complexity. Individual modules (analytics, agents, payments, catalog) are
already isolated enough to extract into services later if a concrete
scaling reason appears — none has yet.

## Why PostgreSQL?
Structured, relational commerce data with real foreign-key integrity
requirements (a payment must reference a real order or campaign, a
customer segment membership must reference a real customer). JSONB
columns are used sparingly for genuinely flexible fields (specifications,
evidence), never as a substitute for real schema.

## Why an LLM at all?
Natural-language reasoning: understanding "what's my biggest opportunity"
or "simulate a 12% discount" requires language understanding that
deterministic code can't provide. See `docs/ai-decisions.md` for exactly
where the AI/deterministic boundary sits.

## Why a deterministic revenue/policy/simulation engine?
Financial correctness and auditability. A number that could have been
generated differently on a different day isn't a number a merchant can
trust with their money. See the Action Pipeline in
`app/agents/pipeline.py`.

## Why a policy engine separate from permissions?
Permissions answer "is the agent allowed to attempt this at all" (a
merchant-configurable ALLOW/APPROVAL/DENY per action). Policy answers "is
this specific request within safe bounds" (a discount cap, a budget cap,
a stock check) — deterministic, re-evaluated on every call, and never
overridable by the agent's own reasoning.

## Why merchant approval for financial actions?
Human control over money movement is non-negotiable. The agent can
propose, simulate, and explain — but a payment link is only ever created
after either explicit approval or an explicit merchant configuration
change to ALLOW that specific action.

## Why Razorpay Test Mode?
Real payment infrastructure without real-money risk, and — per the
product's core positioning — real Razorpay integration is what makes
"sellable to AI buyers" more than a slide.

---

## Razorpay integration: verified sources (Phase 12)

Per the project's rule that Razorpay integration is implemented only from
verified current documentation, never from training-data assumptions
about SDK behavior, the following facts were checked directly against
official Razorpay documentation before any integration code was written:

| Fact | Verified against |
|---|---|
| Orders endpoint: `POST https://api.razorpay.com/v1/orders`, required fields `amount`, `currency`, `receipt` | razorpay.com/docs (Orders API) |
| Payment Links endpoint: `POST https://api.razorpay.com/v1/payment_links`, fields include `amount`, `currency`, `reference_id`, `description`, `customer`, `notify` | razorpay.com/docs/api/payments/payment-links/create-standard |
| Auth: HTTP Basic, `key_id` as username, `key_secret` as password | razorpay.com/docs (curl examples) |
| Amounts are integers in the smallest currency subunit (paise for INR) | razorpay.com/docs (Orders/Payment Links field reference) |
| Webhook signature: `X-Razorpay-Signature` header = HMAC-SHA256 hex digest of the raw request body, keyed with a webhook secret set in the dashboard (distinct from the API key secret); must verify against raw bytes, not re-parsed/re-serialized JSON | razorpay.com/docs (Webhooks — signature verification) |
| Webhook idempotency: `x-razorpay-event-id` header is unique per event | razorpay.com/docs (Webhooks FAQ) |
| Payment Link webhook events: `payment_link.paid`, `payment_link.partially_paid`, `payment_link.cancelled`, `payment_link.expired` | razorpay.com/docs/webhooks/payment-links |
| Payload shape: event/payload/payment_link.entity/payment.entity/order.entity | razorpay.com/docs/webhooks/payment-links (sample payload) |

Verified: August 2026, against the live documentation pages at the URLs
above. If Razorpay's API changes after this date, re-verify before
trusting this table — it is a snapshot, not a permanent contract.

### A correctness detail this surfaced
Our internal ledger (`Payment.amount`, `Campaign.budget_amount`, etc.)
stores whole rupees; Razorpay requires paise. The conversion
(`rupees_to_paise` / `paise_to_rupees` in `app/integrations/razorpay/client.py`)
exists in exactly one place, tested explicitly
(`tests/unit/test_razorpay_client.py`) — a missed or duplicated
conversion at a second call site would have silently created real
payment links for 1/100th (or 100x) the intended amount.

### A schema gap this surfaced
`RevenueAttribution.order_id` is `NOT NULL`, but a campaign-wide payment
link has no pre-existing `Order` — nothing in the system knows which
specific customer will pay until the webhook tells us. Rather than relax
the constraint, the webhook handler creates a real `Order` (+`OrderItem`s,
from the campaign's actual product list) at the moment a paying
customer's email is matched to a known customer record. If no match is
found, the `Payment`/`Campaign` state is still updated (that's factual
regardless of who paid) but no `Order` or `RevenueAttribution` row is
fabricated.

### A retry-safety bug found and fixed
The webhook idempotency check originally treated any prior delivery
attempt for an `event_id` — including a rejected, invalid-signature one —
as a permanent duplicate. Since Razorpay retries webhook delivery with
the same `event_id` until it receives a 2xx, this would have permanently
dropped a legitimate retry after something as ordinary as a briefly
misconfigured webhook secret being fixed. Fixed so only a successfully
processed prior delivery short-circuits as a duplicate; a failed prior
attempt is retried in place (updating the existing row, never inserting a
second one, which would violate the unique constraint on `event_id`).
See `tests/integration/test_razorpay_webhook.py` for both the original
duplicate-prevention test and the new retry-safety regression tests.

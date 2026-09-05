# RevPilot AI — System Overview

Where the AI is actually used, where deterministic code is used instead, how
security is enforced, how failures are handled, the tech stack, and how a request
moves through the backend. Written from direct code inspection (file paths and
function names below are real, not paraphrased from the spec) plus live testing
against a running instance.

---

## 1. Where the AI agent is used vs. where deterministic rules are used

This is the single most important design decision in the product, and the project
is explicit about it in code comments (`app/agents/pipeline.py`, `app/campaigns/simulation.py`).
The rule: **the AI is only ever allowed to understand intent and explain things in
language — it never computes or authorizes a number.**

### Where AI / LLM involvement exists

| Capability | File | What the AI actually does |
|---|---|---|
| Merchant Agent chat | `app/agents/service.py::handle_message` | Turns free text ("create a cross-sell campaign", "what's my biggest opportunity?") into a structured intent |
| AI Buyer chat | `app/buyer/service.py::buyer_query` | Turns free text ("gaming setup under ₹5,000") into a catalog search + ranking request |
| Natural-language replies | both of the above | Composes the human-readable reply string around already-computed, already-validated numbers |

**Important honesty note, found during audit and worth restating here:** with the
default `AI_PROVIDER=mock` (no API key needed to run the whole product), *and
currently even with `AI_PROVIDER=openai`/`gemini` set*, both of the intent-parsing
steps above are implemented as **deterministic keyword/regex routers**
(`_DISCOUNT_PATTERN`, `_intent_terms`, `_extract_budget`, etc.), not real LLM calls.
`app/agents/providers.py` defines a real `AIProvider` abstraction
(`MockAIProvider`, and a factory that would select `OpenAIProvider`/`GeminiProvider`),
but `get_ai_provider()` is never actually invoked from the live chat path, and the
`OpenAIProvider`/`GeminiProvider` classes it references don't exist as files yet.
This is disclosed rather than hidden — the module docstring in `agents/service.py`
says outright: *"NOT claimed as real NLU."* See `docs/implementation-guide.md`
Section 6 for exactly where a real LLM would be wired in without touching anything
downstream.

Everything **downstream** of intent parsing — grounding, math, policy, execution —
is identical whether the intent came from a keyword match or a real LLM call, which
is precisely the point of the architecture: swapping in a real model changes *how
intent is extracted*, not what's trusted afterward.

### Where deterministic code is used (everything that touches money or facts)

| Capability | File | Why it's deterministic |
|---|---|---|
| Revenue metrics, AOV, conversion, repeat rate | `app/analytics/metrics.py` | Pulled directly from order/payment rows, no estimation |
| RFM segmentation | `app/analytics/rfm.py` | Standard recency/frequency/monetary scoring on real transaction history |
| Product affinity (support/confidence/lift) | `app/analytics/affinity.py` | Statistical co-purchase analysis over real order-item pairs |
| Opportunity detection & scoring | `app/opportunities/scoring.py`, `service.py` | Combines the above signals into a 0–100 priority score; conservative assumed rates (e.g. `ASSUMED_ABANDONED_CART_RECOVERY_RATE = 0.12`) are explicitly named constants, always surfaced to the UI as `ESTIMATED`, never presented as measured fact |
| Campaign simulation / what-if | `app/campaigns/simulation.py` | Implements the spec's formula exactly (`Expected Orders = Eligible Customers × Expected Conversion`, etc.) with **zero LLM or randomness involvement** — same inputs always produce the same output, which is what makes "10% vs 12%" comparisons trustworthy |
| Policy engine (discount caps, budget caps, daily campaign caps) | `app/policies/` (`PolicyRule` model + checks in `app/agents/pipeline.py`) | Hard-coded comparisons against merchant-configured thresholds |
| Permission engine (ALLOW / APPROVAL / DENY per action) | `AgentPermission` model, checked in `app/agents/pipeline.py` | Simple lookup table, fail-closed default (unconfigured action → `APPROVAL`, confirmed by `test_get_permissions_returns_fail_closed_default_for_unconfigured_action`) |
| Financial recomputation before every action | `app/agents/pipeline.py`, `app/checkout/service.py` | Every amount is recalculated server-side from current DB state immediately before it's used — an agent-proposed number is never trusted, ever |
| Payment verification, webhook processing | `app/integrations/razorpay/*`, `app/api/webhooks.py` | Signature-verified, idempotent, no AI in the loop at all |
| Revenue attribution | `app/attribution/service.py` | Sums confirmed `RevenueAttribution` rows tied to verified payments; explicitly labels output `attributed_revenue` and refuses to call it `incremental_revenue` without a controlled experiment (`incrementality_note` field) |

**The one-line summary:** the AI decides *what the merchant/buyer meant*; a fixed,
testable, side-effect-free deterministic function decides *what it's worth and
whether it's allowed*.

---

## 2. Security

### Authentication & session
- JWT access tokens (`app/security/auth.py::create_access_token`, HS256, configurable
  expiry), passwords hashed with bcrypt via `passlib` (`app/security/passwords.py`).
- `get_principal` validates the token signature and type on every protected request;
  a malformed/expired token returns `401 INVALID_TOKEN` rather than being silently
  ignored.
- `DEMO_MODE=true` intentionally allows **anonymous** (no token at all) access to
  seeded demo data, so the walkthrough is frictionless — this is documented,
  deliberate product behavior, and `config.py`'s `validate_deployment_safety`
  validator prevents `DEMO_MODE` from being enabled in a non-local environment.

### Authorization
- Every merchant-scoped endpoint calls `ensure_merchant_access(db, merchant_id, principal, allowed_roles=...)`,
  which checks a `UserMerchantRole` row exists for that (user, merchant) pair before
  any data is read or mutated, and additionally checks role membership
  (`OWNER`/`ADMIN`) for mutating actions like approvals, settings changes, and
  campaign pause/cancel.
- This was audited end-to-end: a valid token for merchant A correctly gets
  `403 MERCHANT_ACCESS_DENIED` reading merchant B's dashboard/campaigns/opportunities/
  simulations/attribution — see `tests/integration/test_merchant_scoped_authorization.py`
  (25 tests) and `docs/audit-report-2026-09-04.md` for the fix history.

### Transport & headers
- CORS restricted to a single configured `FRONTEND_URL` (`app/main.py`), not a
  wildcard.
- `RequestIDMiddleware` (`app/core/middleware.py`) stamps every request/response
  with an `x-request-id`, propagated into audit logs and error payloads for
  traceability.
- `x-content-type-options: nosniff`, `x-frame-options: DENY`, `referrer-policy:
  same-origin` set on every response.
- `RateLimitMiddleware` (`app/core/middleware.py`) — in-memory sliding window, 10
  req/min/IP on `/api/v1/auth/*`, 120 req/min/IP elsewhere, `/health` exempt.
  Deliberately simple/single-process (documented as such); a multi-replica
  deployment should swap it for a shared-store limiter.

### Webhook & payment integrity
- `app/integrations/razorpay/webhooks.py` verifies the HMAC-SHA256 signature
  against the **raw** request body before any parsing or DB write.
- `payments.idempotency_key`, `payments.provider_payment_link_id`, and
  `payments.provider_order_id` all carry DB-level unique constraints (the last one
  added during this audit — see item 4 in the audit report) so a duplicate
  webhook delivery or a race between two concurrent requests cannot create two
  Payment rows for the same transaction.
- Amounts are recomputed server-side at confirm/execute time — the frontend or the
  agent can never supply a trusted final amount.

### Secrets
- `.env.example` contains only placeholders; `.gitignore` excludes `.env`.
- `scripts/security_scan.py` is a dependency-free scan for credential-shaped
  literals, run and passing clean.
- Error responses use a single sanitized schema (`app/core/errors.py`) — stack
  traces are never returned to the client.

---

## 3. Failure handling

Centered on the **Failure Lab** (`app/services/failure_lab.py`, exposed at
`/api/v1/demo/failures/*`), which deliberately triggers real failure paths rather
than simulating them cosmetically:

| Scenario | Failure mode | What actually happens |
|---|---|---|
| `payment_timeout` | `provider_timeout` | Payment link creation times out before Razorpay confirms; customer is never charged; campaign transitions to a safe state; retry is available under the same idempotency key |
| `payment_provider_error` | `provider_error` | Razorpay API returns a 5xx/error; same safe-state handling |
| `duplicate_webhook` | `duplicate_delivery` | The same webhook event is delivered twice; the second delivery is detected via the unique `event_id` and ignored — revenue is counted exactly once (verified live and in `tests/integration/test_razorpay_webhook.py`) |
| `invalid_discount` | `policy_violation` | A campaign requests a discount above the merchant's configured cap (e.g. 25% vs a 15% policy max); blocked before it ever reaches Razorpay — verified live |
| `out_of_stock` | `inventory_conflict` | A campaign/checkout targets a product with zero stock; blocked with a clear reason, not a generic error |
| `permission_denied` | — | An action the merchant has explicitly set to `DENY` (e.g. `REFUND_PAYMENT`) is rejected before any external call is attempted |

**General pattern**, consistent across all of the above and in the Action Pipeline
itself (`app/agents/pipeline.py`):

```
Detect  →  Preserve current DB state (no partial writes)  →  Classify
recoverable vs not  →  Retry safely under the same idempotency key if
recoverable  →  Never double-charge or double-count revenue  →  Surface
a clear reason to the user  →  Record an AuditLog row regardless of
outcome
```

- **Emergency Stop** (`app/api/settings.py`, checked in `app/agents/pipeline.py`):
  when enabled, financial actions (campaign execution, payment links, orders) are
  blocked at the pipeline level while read-only analytics, recommendations, and
  simulation remain fully available — verified live: drafting a campaign still
  works, but submitting it for approval is blocked with a clear reason
  ("Discount actions are denied by merchant settings").
- **Critical safety test**, verified live and in `tests/integration/test_critical_safety.py`:
  a 20–25% discount request is blocked against a 15% policy cap; a 10% request is
  correctly routed to `pending_approval`; only after explicit merchant approval does
  execution proceed.

---

## 4. Tech stack (as actually installed and run, not just declared)

**Backend** — `backend/requirements.txt`
```
fastapi 0.115.0          pydantic 2.9.2 / pydantic-settings 2.5.2
SQLAlchemy 2.0.35        alembic 1.13.2
psycopg[binary] 3.2.2    httpx 0.27.2
python-jose[cryptography] 3.3.0 (JWT)   passlib[bcrypt] 4.0.1 (password hashing)
pandas 2.2.2, numpy 1.26.4, scikit-learn 1.5.1   (analytics)
pytest 8.3.2 / pytest-cov 5.0.0, ruff 0.6.4       (test + lint)
```
Python 3.12 (target-version `py311` in `pyproject.toml`).

**Frontend** — `frontend/package.json`
```
react 19.2, react-dom 19.2, react-router-dom 7.18
@tanstack/react-query 5.101   (server state / caching)
recharts 3.10                 (charts)
react-hook-form 7.85 + zod 4.4  (forms/validation)
framer-motion 13.1            (animation)
lucide-react 1.33             (icons)
Vite 8.2 + @vitejs/plugin-react 6.0, TypeScript, Tailwind (via @tailwindcss/vite 4.3)
oxlint 1.75                   (lint)
```

**Database:** PostgreSQL 16, managed via Alembic migrations
(`database/migrations/versions/`) — currently 5 migrations, all applied cleanly
against a fresh database during this audit (initial schema → unique constraints on
policy/permission rows → unique constraint on payment link ID → attribution
timestamp → unique constraint on order ID, the last one added during this audit).

**AI:** Provider abstraction present (`app/agents/providers.py`); `MockAIProvider`
is what actually runs today in every configuration (see Section 1's honesty note).

**Payments:** Razorpay Test Mode via `app/integrations/razorpay/`, with a parallel
`MockPaymentProvider` (`app/integrations/razorpay/mock_provider.py`) selected via
`factory.py` when `PAYMENT_PROVIDER=mock` — used by the seeded demo and the entire
test suite.

---

## 5. Backend request workflow

Every request follows the same layered path — verified concretely by tracing a real
`POST /api/v1/agent/checkout/confirm` call end-to-end during this audit:

```
HTTP request
   │
   ▼
Middleware stack (app/main.py, outer → inner):
   RequestIDMiddleware   → stamps x-request-id
   RateLimitMiddleware   → 429s abusive traffic before it does any work
   CORSMiddleware        → restricted to FRONTEND_URL
   │
   ▼
FastAPI route (app/api/*.py)
   - Pydantic request-body validation (auto-rejects malformed input, 422)
   - Depends(get_principal) → validates JWT if present, else None in DEMO_MODE
   - ensure_merchant_access(db, merchant_id, principal, allowed_roles=...) → 401/403
   │
   ▼
Application service (app/checkout/, app/campaigns/, app/agents/, app/attribution/, ...)
   - Orchestrates the actual business operation
   - Delegates money math to deterministic modules (Section 1), never inlines it
   │
   ▼
Domain / integration layer
   - app/integrations/razorpay/*  → RazorpayProvider or MockPaymentProvider (factory.py)
   - Idempotency check BEFORE any external call
   │
   ▼
Repository / ORM (SQLAlchemy models in app/models/*.py)
   - Transaction boundary: webhook/payment state changes commit atomically —
     no partially-applied financial state on failure
   │
   ▼
PostgreSQL
   │
   ▼
AuditLog row written (app/models/ops.py) regardless of success/failure/block
   │
   ▼
Unified response
   - Success → typed JSON per the route's response
   - Failure → app/core/errors.py's single sanitized error schema
     {"error": {"code", "message", "request_id", "details"}} — no stack traces
```

**Agent-specific variant** (the one place with an extra hop): a chat message goes
through `AgentSession` → keyword-router intent parsing (`agents/service.py`) →
Pydantic schema validation (`agents/schemas.py`) → the same Action Pipeline
(`agents/pipeline.py`, which itself runs Policy Check → Permission Check → Risk
Classification → Financial Recalculation → Simulation → Approval-or-Execute) → the
same deterministic/integration/repository chain as above. This is the "no
shortcuts" pipeline described in the build spec, and it is the same pipeline
whether the intent came from the keyword router or (once wired) a real LLM.

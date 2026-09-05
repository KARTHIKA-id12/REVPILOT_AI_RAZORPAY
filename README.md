# RevPilot AI

**The AI revenue agent for merchants — and the machine-readable commerce
layer for AI buyers.**

> Find revenue. Explain the opportunity. Simulate the impact. Act only
> within the merchant's rules. Verify. Measure. Learn.

Built for the Razorpay AI Builder Internship 2026 — Track 1: AI Growth &
Agentic Commerce.

## What this is (and isn't)

Most commerce AI helps *buyers* discover products. RevPilot helps
*merchants* discover their next revenue opportunity — and, on the other
side, exposes the merchant's catalog so AI buyers can discover, compare,
and check out conversationally.

The core architectural bet: **the LLM never has unrestricted access to
money.** It reads data, proposes actions, and explains itself. Every
proposal is re-priced, policy-checked, permission-checked, and (by default)
human-approved by a deterministic backend before it ever reaches Razorpay.

```
LLM → structured intent → policy engine → permission engine
    → merchant approval → deterministic service → Razorpay
    → webhook → verification → audit
```

## Status

This repo is being built phase by phase (see `docs/roadmap-testing-deployment.md`).

- [x] Phase 0 — Product contract (`docs/`)
- [x] Phase 1 — Foundation: repo, Docker, health check, lint/test scaffolding
- [x] Phase 2 — Database: 29 domain tables, Alembic migrations, verified against real Postgres
- [x] Phase 3 — Demo data: TechNest merchant, 1,050 customers, 4,799 orders, real affinity/RFM signal
- [x] Phase 4 — Analytics engine: RFM, product affinity, opportunity detection/scoring — 39 real opportunities from seeded data, exposed via `/api/v1/dashboard/*` and `/api/v1/opportunities`
- [x] Phase 5 — Merchant dashboard: real metrics, revenue trend chart, top products, top opportunities widget — all live-wired, zero hard-coded numbers
- [x] Phase 6 — Opportunity detail pages: full evidence display, assumptions clearly labeled, priority score
- [x] Phase 7 — AI Growth Agent: policy engine, permission engine (with Emergency Stop), risk classification, deterministic simulation, the mandatory Action Pipeline, agent chat grounded in real data, Agent Chat UI + Approval Center UI live-wired end to end
- [x] Phase 8/9 — Settings UI: Agent Permissions (ALLOW/APPROVAL/DENY per action), Policy Guardrails (discount cap, budget cap, stock/margin rules), Emergency Stop toggle — all live-wired, changes take effect on the very next agent action
- [x] Phase 10 — Campaign Simulator UI: side-by-side what-if discount comparison, driven by a standalone `/api/v1/simulations/compare` endpoint (works from the UI directly, not just through agent chat)
- [x] Phase 11 — Campaigns list/detail: full lifecycle view (status, approval history, payment links, chronological audit trail), pause/cancel with status-transition validation
- [x] Phase 12 — Real Razorpay integration: Orders + Payment Links APIs, webhook signature verification, idempotent webhook processing, revenue attribution — implemented strictly from verified official documentation (see `docs/product-decisions.md`)
- [x] Phase 13 — Failure Lab: 6 real failure scenarios (payment timeout, payment provider error, duplicate webhook, policy violation, out-of-stock, permission denied), every one driving the actual production pipeline through a genuine failure and back — nothing scripted
- [x] Phase 14 — Campaign Orchestrator: the full Opportunity → Agent → Simulation → Policy → Approval → Razorpay → Webhook → Attribution loop, closed out with a dedicated single-test full-chain assertion (see below) — this had been built piecemeal across Phases 7/10/12 but never given its own explicit checkpoint until a full wiring audit caught the gap
- [x] Phase 15 — Agent-readable catalog: machine-readable commerce API for AI buyers (`/api/v1/agent/*`), purely deterministic — every price, stock count, and product relationship is a live DB read, never AI-generated
- [x] Phase 16 — AI Buyer: intent-aware catalog recommendations, relation-backed bundles, product comparison, persistent conversational cart, and budget enforcement (`docs/ai-buyer.md`)
- [x] Phase 17 — Checkout: server-recomputed preview, explicit consent gate, provider order creation, payment verification, demo payment mode, and order confirmation
- [x] Phase 18 — Revenue attribution: verified payment settlement, campaign/AI-buyer attribution, inventory settlement, summary metrics, and incrementality-safe reporting
- [x] Phase 19 — Audit Ledger, Agent Traces, Action Center, merchant-scoped notifications, and Control Room UI (`docs/operations.md`)
- [x] Phase 20 — Failure Lab with real-path provider, webhook, policy, inventory, and permission failures plus recovery traces
- [x] Phase 21 — JWT authentication, merchant membership authorization, role-gated settings/approvals, security headers, and credential scan (`docs/security.md`)
- [x] Phase 22 — API-level E2E smoke flows for the merchant console and AI-buyer checkout (`docs/e2e-testing.md`)
- [x] Phase 23 — Responsive shell, keyboard accessibility, reduced-motion support, responsive chart labeling, and shared UI motion (`docs/ui-polish.md`)
- [x] Phase 24 — Production Docker topology with PostgreSQL, Alembic startup, Caddy HTTPS, environment-only credentials, and Razorpay webhook routing (`docs/deployment.md`)
- [x] Phase 25 — Deterministic demo seed/runbook, Razorpay Test Mode checklist, Failure Lab sequence, five-minute pitch, and demo smoke check (`docs/demo-runbook.md`, `docs/pitch.md`)
- [x] Final quality check — validation matrix and environment-specific verification commands (`docs/final-quality-check.md`)

## Full-system wiring audit

Every phase above has been individually verified, but a system this size
also needs periodic end-to-end confirmation that nothing has drifted
between phases. This was run as an explicit audit (not assumed):

- Every backend router is imported and registered in `app/main.py` — no
  orphaned endpoints (confirmed by enumerating `app.routes` directly).
- Every frontend nav item resolves to a real page — no dead links, no
  forgotten `ComingSoonPage` placeholders left where a real page now exists.
- `alembic check` reports zero schema drift between models and the
  applied migrations.
- **A genuinely fresh-environment smoke test**: a brand-new checkout, a
  brand-new database, migrations run from zero, demo data seeded, the
  full test suite (124 tests) run, and every phase's key endpoint hit
  over live HTTP — all from a copy of the repo with no leftover state
  from development.

That fresh-environment test caught a real bug: `Settings`' `.env`
resolution was relative to the **current working directory**, not to
`backend/`. Running `python scripts/seed_demo.py` from the repo root (as
the README's own Quickstart instructs) found no `.env` there, silently
fell back to the in-code default `DATABASE_URL`, and seeded whatever
database happened to already exist at that default connection string —
not the fresh one just created for the test. This had been masked all
session by always keeping a `.env` copy at both the repo root and
`backend/`. Fixed by anchoring `env_file` to `backend/`'s absolute path in
`app/core/config.py`, regardless of the caller's working directory —
re-verified with the exact same fresh-environment test, run twice: once
proving the bug (wrong database silently written to), once proving the
fix (correct database found regardless of CWD, original data confirmed
untouched by the mistaken run).

`/health` currently returns `"database": "healthy"` once Postgres is up and
migrations are applied — verified end-to-end, not asserted.

## AI Growth Agent (Phase 7)

The architectural core of the product's safety story. Every agent action
tool call passes through one mandatory sequence — no exceptions, no
shortcuts:

```
validate (Pydantic) → permission check → policy check
→ financial recalculation (never trusts agent-supplied numbers)
→ simulation → approval gate → idempotency key → execute → verify → audit
```

- `app/policies/rules.py` — deterministic policy engine (discount cap,
  budget cap, daily campaign volume, stock availability). Pure functions,
  re-read from the DB on every call, never cached or trusted from a
  request payload.
- `app/policies/permissions.py` — permission engine. Fails closed (an
  unconfigured action requires approval, never implicit allow). Emergency
  Stop is re-evaluated on every single call, not cached at session start.
- `app/campaigns/simulation.py` — the spec's exact simulation formulas,
  deterministic, same inputs always produce the same output.
- `app/agents/pipeline.py` — the Action Pipeline itself, with inline
  documentation of every loophole it's designed to close.
- `app/agents/service.py` — session orchestration. In demo mode
  (`AI_PROVIDER=mock`, the default, no API key needed), intent routing
  uses a documented keyword router — explicitly NOT claimed as real NLU —
  so the full tool-calling/pipeline loop runs end-to-end without an
  external dependency.

**56 backend tests passing**, including 9 lifted directly from the spec's
critical safety scenarios: a 20% discount request is blocked outright, a
10% request requires approval and only executes after a merchant approves
it, double-approving is refused, out-of-stock products block a campaign,
over-budget campaigns are blocked, and asking about a nonexistent product
gets an honest "I couldn't find that" rather than an invented answer.

Three real bugs were found and fixed while building this phase (not
staged — genuinely caught by writing and running these tests): a
too-early discount check that broke the spec's staged approval flow, a
missing DB uniqueness constraint that let duplicate permission rows crash
the permission gate instead of failing closed, and a cross-phase bug
where acting on an opportunity could break the next analytics refresh
with a foreign-key violation. All three now have permanent regression
tests (`tests/integration/test_critical_safety.py`).

A fourth was found while wiring the frontend and doing a full-stack demo
walkthrough: `scripts/seed_demo.py`'s reset logic predated campaigns,
approvals, agent sessions, and customer segments — so resetting the demo
after any real usage (an agent chat, an approved campaign) crashed with a
foreign key violation instead of cleanly restoring state. Fixed with an
explicit, dependency-ordered `_reset_merchant` function and a regression
test (`tests/integration/test_demo_reset.py`) that builds a merchant with
one of everything and asserts the reset doesn't crash.

The Agent Chat and Approval Center pages are now live-wired in the
frontend (`/agent`, `/approvals`) — every field rendered was verified
against the real backend response shape over HTTP, not assumed from the
TypeScript types alone.

## Settings (Phases 8–9): permissions, policies, Emergency Stop

`/settings` in the frontend, backed by `/api/v1/settings/*`:

- **Agent Permissions** — per-action ALLOW/APPROVAL/DENY, editable from
  the UI. Every action_code and mode is validated against a canonical
  registry (`app/policies/constants.py`) — an unrecognized code is
  rejected with a 422, never silently stored (storing a permission for a
  made-up code the Action Pipeline never checks would give false
  confidence that a control exists when it does nothing).
- **Policy Guardrails** — discount cap, budget cap, daily campaign limit,
  single-transaction cap, stock/margin rules, with server-side bounds
  validation (a >100% discount cap or negative budget is rejected before
  it ever reaches the policy engine).
- **Emergency Stop** — verified end-to-end over live HTTP, not just at
  the unit level: enabling it through the real settings endpoint and then
  asking the agent to create a campaign correctly still allows drafting
  (non-financial) but blocks discount commitment (financial) with "denied
  by merchant settings" — exactly the documented behavior.

Two more real bugs were found and fixed while building this phase:
1. **A Pydantic v2 / FastAPI infrastructure bug**, not specific to this
   endpoint: a `@field_validator` raising `ValueError` produces an error
   dict containing the raw exception object in `ctx.error`, which is not
   JSON-serializable. Passing that straight through the unified error
   handler crashed with a `TypeError`, turning every clean 422 from any
   custom validator anywhere in the app into an opaque 500. Fixed by
   sanitizing `ctx.error` to a string before serialization
   (`app/core/errors.py`), with a dedicated regression test
   (`tests/unit/test_error_handling.py`) — this bug would have silently
   broken validation error messages app-wide, not just in Settings.
2. Confirmed (rather than assumed) that the unique constraint added in
   Phase 7 makes permission upserts safe from the settings UI — updating
   the same action twice always updates the existing row, never inserts
   a duplicate.

**70 backend tests passing.**

## Campaign Simulator (Phase 10)

`/simulator/:opportunityId` in the frontend (linked from every opportunity
detail page), backed by a new standalone `POST /api/v1/simulations/compare`
endpoint. This is the same deterministic math from Phase 7's agent
`SIMULATE_CAMPAIGN` tool, but now reachable directly from the UI without
going through chat — side-by-side scenario cards across multiple discount
levels, with the best-ROI scenario highlighted.

The reach/AOV/confidence computation was extracted into a single shared
module (`app/campaigns/inputs.py`) used by BOTH the agent pipeline and
this new endpoint, specifically so there is one implementation to keep
correct rather than two that could silently drift apart and disagree —
verified with a test that asserts both call sites return byte-identical
results for the same inputs.

Two more real bugs were found and fixed while building this phase:

1. **A permanent data leak in the test suite itself.** Several
   integration tests call Action Pipeline functions that `db.commit()`
   internally (agent actions must be durable mid-test), which means a
   fixture's `db.rollback()` in teardown was a silent no-op — the data
   was already committed. This had been quietly leaking a throwaway
   "Test Merchant" into the shared development database on every test
   run since Phase 7; by the time this was caught, **169 orphaned test
   merchants** had accumulated (confirmed by direct SQL query, not
   assumed). Fixed at the root: the merchant-deletion logic was extracted
   out of `scripts/seed_demo.py` into a proper shared service
   (`app/services/merchant_cleanup.py`), and every leaking fixture now
   calls it explicitly in teardown instead of relying on `rollback()`.
   The 169 orphans were purged using that same fix, verified down to
   exactly 1 merchant (TechNest) in the database afterward, with
   TechNest's own data (12 products, 1,050 customers, 4,411 paid orders)
   confirmed untouched.
2. Cross-merchant isolation for the new Simulator endpoint was verified
   as a first-class test, not an afterthought — an `opportunity_id`
   belonging to a different merchant correctly returns 404 rather than
   leaking that merchant's data.

## Campaigns (Phase 11)

`/campaigns` and `/campaigns/:id` in the frontend, backed by
`/api/v1/campaigns/*`. The detail page shows the full lifecycle: product
names resolved from IDs, chronological approval history (with the exact
policy result recorded at request time), payment links (clearly labeled
"Demo Payment Mode" vs. "Razorpay Test Mode" depending on the active
provider), and a chronological audit trail spanning
draft → approval-requested → approved → executed. Pause/cancel enforce
valid status transitions server-side (pausing an already-paused campaign,
or cancelling a completed one, is rejected with `409`, not silently
accepted).

Building this surfaced a real gap: `Campaign.expected_revenue_amount` and
`actual_revenue_amount` existed in the schema since Phase 2, but nothing
had ever written to them — every campaign would have silently shown ₹0
expected revenue despite a full simulation having already been computed
and frozen at approval time. Fixed by populating
`expected_revenue_amount` from that same frozen simulation at execution,
with a regression test.

A second, more consequential bug was found while writing this phase's
tests: **169 orphaned test merchants had silently accumulated** in the
shared development database. Root cause — several integration tests call
Action Pipeline functions that `db.commit()` internally (agent actions
must be durable mid-test), so a fixture's `db.rollback()` in teardown was
a no-op; the data was already committed. This wasn't assumed, it was
confirmed with a direct SQL count. Fixed at the root: the merchant-
deletion logic was extracted into a proper shared service
(`app/services/merchant_cleanup.py`, used by both the demo reset script
and test teardown), the leaking fixtures now call it explicitly, and a
new maintenance utility (`scripts/purge_test_merchants.py`) exists for
the residual case no fixture design can fully prevent — a test process
killed mid-run skips teardown entirely, by definition. Verified down to
exactly 1 merchant (TechNest) in the database, full backend suite
re-confirmed to leak zero net rows afterward.

**83 backend tests passing.**

## Real Razorpay integration (Phase 12)

Implemented strictly from verified official documentation — every
endpoint, field name, and behavior was checked against live Razorpay docs
before writing any code (full source table in `docs/product-decisions.md`).

- **Orders & Payment Links** (`app/integrations/razorpay/client.py`):
  real `RazorpayProvider` implementing the same `PaymentProvider`
  interface `MockPaymentProvider` has used since Phase 1 — switching
  providers touches zero business logic, only `PAYMENT_PROVIDER=razorpay`
  plus real credentials in `.env`.
- **Webhooks** (`app/api/webhooks.py`, `POST /api/v1/webhooks/razorpay`):
  signature-verified against the raw request body, idempotent via
  Razorpay's `x-razorpay-event-id` header, updates `Payment` and
  `Campaign` state, and creates a real `Order` + `RevenueAttribution`
  when the paying customer's email matches a known customer — never
  fabricated when it doesn't.

**Four real bugs found and fixed while building this phase** (not staged
— found by writing and running the tests, and by manually walking the
full demo flow end-to-end over HTTP against real TechNest data):

1. **A real currency-unit bug, caught before it could ship**: our ledger
   stores whole rupees, Razorpay requires paise. The conversion is
   isolated to one tested function — a missed conversion at a second call
   site would have silently created real payment links for 1/100th (or
   100×) the intended amount.
2. **A schema/logic mismatch**: `RevenueAttribution.order_id` is
   `NOT NULL`, but a campaign-wide payment link has no order until a
   customer actually pays. Fixed by having the webhook handler create a
   real `Order` (from the campaign's real product list) at confirmation
   time — not fabricated data, a genuine record of what was purchased —
   rather than weakening the constraint.
3. **A permanent-block retry bug**: the original idempotency check
   treated any prior delivery for an event — even a rejected,
   invalid-signature one — as a permanent duplicate. Since Razorpay
   retries with the same event ID until it gets a 2xx, this would have
   silently dropped a legitimate retry after fixing something as ordinary
   as a briefly misconfigured webhook secret.
4. **A latent crash bug**: two invalid-signature deliveries with the same
   event ID would have hit the unique constraint and thrown an unhandled
   `IntegrityError` — never actually triggered before this was found and
   fixed, but a real gap.

Also fixed along the way: the shared `merchant_cleanup` service (built in
Phase 11) was missing `PaymentEvent` cascade deletion, caught the moment
a test actually created one.

Verified end-to-end over real HTTP against TechNest: agent chat creates a
campaign → approved → mock payment link → a properly-signed webhook
confirms payment → campaign flips to `completed` with
`actual_revenue_amount` exactly matching `expected_revenue_amount` → a
real `Order` and `attributed` `RevenueAttribution` row exist, matched to
an actual seeded customer by email.

**101 backend tests passing.**

## Failure Lab (Phase 13)

`/failure-lab` in the frontend, backed by `/api/v1/demo/failures/*`.
Every scenario here drives the **real** production code path — the exact
same policy engine, permission engine, payment pipeline, and webhook
endpoint used everywhere else in the product. Nothing is a scripted
response.

- **Payment timeout / payment provider error**: a single-shot failure
  injector (`app/services/failure_injection.py`) wraps the real payment
  provider so the *next* call genuinely raises `RazorpayTimeoutError` or
  `RazorpayAPIError` — the same exception classes a real Razorpay outage
  would raise. The Action Pipeline's real error handling (built in Phase
  12) catches it, marks the campaign `failed`, records a full audit
  entry, and — crucially — a retry with the same idempotency key then
  succeeds for real, demonstrating DETECTED → PROTECTED → AUDITED →
  RECOVERED end to end.
- **Duplicate webhook**: sends the same properly HMAC-signed payload
  twice through the actual `/api/v1/webhooks/razorpay` endpoint via an
  in-process ASGI client — not a hand-rolled reimplementation of the
  idempotency logic — and shows real revenue figures proving it was
  counted exactly once.
- **Policy violation / out-of-stock / permission denied**: real 25%
  discount request genuinely blocked by the real policy engine (with the
  actual configured cap in the error message), a real product temporarily
  marked out-of-stock and genuinely blocking a real campaign draft, a
  real permission temporarily set to DENY genuinely blocking a real
  action — each scenario restores the temporarily-changed state
  afterward, verified by a dedicated test that the demo never corrupts
  real catalog or settings data.

While building this, catching a subtle authenticity gap in my own first
draft mattered as much as the scenarios themselves: the initial duplicate-
webhook implementation hand-rolled a simplified version of the
idempotency check rather than calling the real webhook endpoint function
— which meant it wasn't actually testing what it claimed to. Rewritten to
round-trip through the real endpoint instead.

**109 backend tests passing.**

## Agent-Readable Catalog (Phase 15)

`/api/v1/agent/*`, fully documented in `docs/agent-commerce-api.md` — the
contract another AI agent could integrate against without ever seeing
RevPilot's frontend. This is where the AI Buyer story begins.

- `GET /agent/catalog`, `/agent/catalog/search`, `/agent/products/{id}`,
  `/agent/categories`, `/agent/recommendations` — every one backed by
  `app/catalog/agent_catalog.py`, a module with zero LLM calls and zero
  inputs that could let a price, stock count, or product relationship be
  invented rather than read.
- **Discontinued products never surface.** Only `status == "active"`
  products appear anywhere on this surface.
- **Out-of-stock products are still visible but never recommended or
  marked purchasable** — `purchase.available` is the single field an AI
  buyer should check, and it's computed from real `stock_status`, not
  cached or estimated.
- **`related_products` / `frequently_bought_with` / `compatible_products`**
  come directly from the real `product_relations` table populated in
  Phase 3 — verified against TechNest's actual data (Keyboard →
  `frequently_bought_with`: Mouse; → `related_products`: Desk Mat, exactly
  matching the seeded relationships, not inferred or guessed).
- **Recommendations are deterministic keyword matching against real
  `use_cases`/`tags`**, explicitly not an LLM call (see
  `docs/ai-decisions.md`) — verified live: "gaming setup" under ₹5,000
  against real TechNest data correctly returns five real in-stock,
  in-budget products ranked by match count then price.
- **A query for something the catalog can't serve returns an honest
  empty result** (`found: false`), never a plausible-sounding
  fabrication — this is the same anti-hallucination discipline the
  merchant-facing agent already has, now enforced on the buyer-facing
  surface too.
- **Tenant isolation verified as a first-class test**: merchant A can
  never list or fetch merchant B's products, even by a technically valid
  product ID — a wrong ID and someone else's product return the
  identical 404, so a caller can't distinguish the two.

**123 backend tests passing.**

Try it:
```bash
python scripts/seed_demo.py   # if not already seeded
uvicorn app.main:app --reload
```
```bash
curl -X POST localhost:8000/api/v1/agent/sessions -H "Content-Type: application/json" \
  -d '{"merchant_id": "<technest-id-from-/api/v1/merchants>"}'
curl -X POST localhost:8000/api/v1/agent/sessions/<session-id>/messages \
  -H "Content-Type: application/json" -d '{"content": "What is my top revenue opportunity?"}'
```

## Analytics engine

```bash
python scripts/run_analytics.py     # runs RFM + affinity + opportunity detection against TechNest, prints a summary
```

Everything is deterministic — no LLM involved (see `docs/ai-decisions.md`
principle: revenue math, RFM, affinity, and opportunity scoring are all
plain pandas/numpy over real transactions, unit-tested with synthetic data
and integration-tested against the real seeded merchant):

- **RFM segmentation** (`app/analytics/rfm.py`) — rank-percentile quintile
  scoring, rule-based segment assignment into 9 segments (Champions, Loyal,
  Potential Loyalists, New, At Risk, Dormant, High Value, Price Sensitive,
  Needs Attention). Customers with zero paid orders are excluded, never
  forced into a segment.
- **Product affinity** (`app/analytics/affinity.py`) — real support/
  confidence/lift via basket-incidence matrix multiplication. On the
  seeded data, Keyboard→Mouse shows **lift ≈ 2.13×**, hand-verified
  against raw SQL.
- **Opportunity scoring** (`app/opportunities/scoring.py`) — cross-sell,
  bundle, abandoned-cart, reactivation, and repeat-purchase detection,
  each producing `reach_count`, `confidence`, `estimated_revenue_amount`,
  `risk_level` (stock-aware), and a 0–100 `priority_score` normalized
  across the candidate set. Every projected number is tagged with its
  assumption in `evidence_json` — nothing is presented as fact that isn't
  measured.

Live example from the seeded merchant: **Monitor Light → Gaming Monitor**
cross-sell, 224-customer reach, 2.13× lift, ~₹641K estimated revenue,
low risk (target in stock) — `priority_score: 100`.

## Frontend (merchant console)

The dashboard and opportunity pages are fully wired to the live backend —
`/api/v1/merchants`, `/api/v1/dashboard/*`, `/api/v1/opportunities` — no
mock data, no hard-coded numbers. Every route in the sidebar either works
or shows an explicit "not built yet, here's the phase it lands in" state
— never a silent dead link (see `src/pages/ComingSoonPage.tsx`).

```bash
cd frontend && npm install && npm run dev
```

Visit `http://localhost:5173`. In dev, Vite proxies `/api/*` to the
backend (`vite.config.ts`), so no CORS setup is needed locally.

## Demo data

```bash
python scripts/seed_demo.py     # deterministic (seed=42), idempotent — wipes & regenerates TechNest
```

Generates TechNest (gaming/productivity accessories) with:
- 12 products across 6 categories, with real compatibility/affinity metadata
- 1,050 customers across 8 behavioral archetypes (champion, loyal, potential
  loyalist, new, at-risk, dormant, high-value, price-sensitive) — profiles
  drive generation only; segments/RFM scores are *derived* in Phase 4, never
  written here
- 4,799 orders (92% paid / 5% failed / 3% cancelled), seasonally weighted
  across the last 12 months, with realistic baskets
- 222 abandoned carts (including anonymous browsing sessions)

Validated, not just generated — e.g. Keyboard→Mouse shows **39.8% confidence
vs. an 18.7% baseline, a ~2.1× lift**, computed by hand against the seeded
transactions (see commit history / demo script). A restorable dump lives at
`database/seeds/technest_demo.dump` (see `database/seeds/README.md`).

Demo login: `owner@technest.demo` / `RevPilotDemo123!`

## Docs

- `docs/architecture.md` — system architecture, the two loops, the safety boundary
- `docs/domain-model.md` — full ER design
- `docs/api-contract.md` — internal + agent-facing API surface
- `docs/agent-tools-permissions-policy.md` — tool registry, permissions, policy, risk
- `docs/design-system.md` — IA + visual design language
- `docs/roadmap-testing-deployment.md` — phase checklist, testing & deployment strategy

## Quickstart (local, no Docker)

Backend:
```bash
cd backend
pip install -r requirements.txt --break-system-packages
cp ../.env.example ../.env   # then edit as needed
alembic upgrade head          # applies database/migrations against DATABASE_URL
uvicorn app.main:app --reload
```

Frontend:
```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:5173`. The dashboard's status bar shows live
backend health (`/health`), including DB, AI provider mode, and payment
provider mode — nothing on that bar is hard-coded.

## Quickstart (Docker)

```bash
cp .env.example .env
docker compose up --build
python scripts/health_check.py
```

## Payment modes

- **Demo Payment Mode** — `PAYMENT_PROVIDER=mock`, no Razorpay credentials
  needed. Uses `MockPaymentProvider`; the UI always labels this clearly as
  demo mode, never presented as a real transaction.
- **Razorpay Test Mode** — set `PAYMENT_PROVIDER=razorpay` plus
  `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` / `RAZORPAY_WEBHOOK_SECRET` in
  `.env`. Implemented in Phase 12 against current official Razorpay docs.

## License

TBD.

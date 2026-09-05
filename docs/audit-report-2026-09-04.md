# RevPilot AI — Full Project Audit

**Date:** 2026-09-04
**Scope:** Full codebase audit for the Razorpay AI Builder Internship 2026, Track 1 (AI Growth & Agentic Commerce) — checked for other-AI-tool traces, secrets/security leaks, duplicate data, broken wiring, Razorpay/payment-layer correctness, AI agent safety, and failure handling.

**Method:** Not a read-through. The project was actually built and run: Postgres stood up, backend dependencies installed, all Alembic migrations applied, demo data seeded (1,050 customers / 4,799 orders), the FastAPI server booted and hit live over HTTP, the frontend installed/typechecked/linted/built, and the full pytest suite executed and re-executed after every fix.

---

## Summary

The project is genuinely well-architected and mostly does what the spec asks: real deterministic analytics, a properly gated agent action pipeline, correct Razorpay abstraction, working idempotency, a real Failure Lab, and no fabricated metrics or fake AI. No trace of any other AI coding tool (Replit, Lovable, Bolt, Cursor, Windsurf, v0, etc.) was found anywhere in the codebase.

Six real issues were found and fixed, the most important of which was a genuine authorization gap. All fixes are verified: **159/159 backend tests pass** (up from 134, including 25 new regression tests), frontend **typechecks and builds cleanly**, and every fix was additionally re-verified live against the running server, not just via unit tests.

---

## Issues found and fixed

### 1. [Critical] Merchant-scoped data endpoints had no authorization check at all
**Files:** `backend/app/api/dashboard.py`, `campaigns.py`, `opportunities.py`, `simulations.py`, `attribution.py`, `merchants.py`

Six route files never called `get_principal`/`ensure_merchant_access`, unlike the other five API files (`agent.py`, `approvals.py`, `merchant_data.py`, `ops.py`, `settings.py`), which enforce it correctly. Two of the files even had explicit leftover comments admitting it (`"# open for now since auth isn't wired yet"`, `"# Pre-auth convenience endpoint... Once Phase auth lands, this narrows..."`) — auth *did* land in later phases, but these files were never revisited.

**Precise impact** (verified live before fixing): a request with an **invalid/garbage bearer token**, or a **valid token belonging to a user with no relationship to that merchant**, was silently ignored rather than rejected — the request proceeded as if unauthenticated. A signed-in user could read *any* merchant's revenue, campaigns, opportunities, simulations, and attribution data, not just their own, and could pause/cancel another merchant's campaigns. This is exactly the failure mode item §106 in the build spec asks to be tested for ("unauthorized merchant cannot access another merchant").

To be precise about what was *not* broken: anonymous requests with no `Authorization` header at all correctly still get through in `DEMO_MODE` — that's intentional, documented product behavior (`docs/security.md`) shared by the correctly-wired endpoints too, and is what lets the seeded demo work without a login step. The bug was specifically that a *supplied* token (bad or cross-tenant) wasn't validated on these six files.

**Fix:** added `principal: Principal | None = Depends(get_principal)` + `ensure_merchant_access(...)` to every route in all six files, matching the existing correct pattern exactly. Mutating actions (`campaign pause/cancel`, `opportunity refresh`) were additionally restricted to `OWNER`/`ADMIN` roles, matching how `approvals.py`/`settings.py` already restrict their mutating routes. `merchants.py`'s list endpoint now scopes to the signed-in user's own merchants (falls back to "all active merchants" only when there is no token at all, preserving demo convenience).

**Regression coverage:** new file `backend/tests/integration/test_merchant_scoped_authorization.py` (25 tests) — asserts a valid token for merchant A gets `403 MERCHANT_ACCESS_DENIED` reading merchant B's data across all six files, a garbage token gets `401 INVALID_TOKEN` instead of being silently ignored, and a valid same-merchant token still gets `200`. Also live-verified against the running server (see below).

### 2. [High] AI Buyer checkout preview was completely broken
**File:** `backend/app/checkout/service.py`

`preview_checkout()` destructured `cart, _ = _cart_or_error(...)` (discarding the second value) but then referenced an undefined `state` variable a few lines later — a plain `NameError`. Every call to `POST /api/v1/agent/checkout/preview` would 500. This is the exact step in the winning-demo script (§128, §47) between adding items to cart and confirming a purchase — the AI Buyer flow was non-functional at the one step that actually shows the customer their order total before paying.

**Fix:** corrected the destructuring to `cart, state = _cart_or_error(...)`. Verified live end-to-end: add-to-cart → preview → confirm → verify → duplicate-verify (idempotency) all now work correctly through the real HTTP API.

### 3. [Medium] Frontend had a fully-working backend auth system with no UI to reach it
**Files:** new `frontend/src/services/auth.ts`, `frontend/src/pages/LoginPage.tsx`; edited `App.tsx`, `layouts/AppShell.tsx`

The backend's login/signup/JWT flow works correctly (confirmed via direct API tests), but nothing in the frontend ever called it — `localStorage` was never written anywhere, so the app only ever ran in the anonymous `DEMO_MODE` path. This contradicts your own demo script (§95, step 2: *"Login with demo credentials"*) and the final checklist (*"Login works"*, *"Signup works"*), and — combined with issue #1 — meant the authorization layer was effectively unreachable and untested from the UI.

**Fix:** added a minimal login page (pre-filled with the seeded demo credentials) and a sign-in/sign-out control in the header, wired to the real `/api/v1/auth/login` and `/api/v1/auth/me` endpoints. Deliberately does **not** gate the rest of the app behind a login wall, since the frictionless anonymous demo walkthrough is intentional, documented product behavior — this only makes the login path an actually-reachable option, as the spec requires.

### 4. [Low] Duplicate-payment race window on the Order/AI-Buyer checkout path
**Files:** `backend/app/models/commerce.py`, new migration `8a1f2c4d9e01_unique_constraint_on_payment_provider_.py`

`payments.provider_payment_link_id` and `payments.idempotency_key` already had DB-level unique constraints, but `provider_order_id` (used by the direct-order / AI Buyer checkout path) did not. The application-level idempotency check already prevents the common case, but this closes the remaining race window (two concurrent requests both passing the idempotency check before either commits) and brings the Order flow's data-integrity guarantee up to the same level as the Payment Link flow's, per your own §116/§36 no-duplicate-revenue requirement.

**Fix:** added `UniqueConstraint("provider_order_id", ...)` + Alembic migration. `NULL` values remain unrestricted (mock/campaign payments that never set this field are unaffected). Verified migration applies cleanly and full test suite still passes.

### 5. [Medium] No rate limiting anywhere, despite §71 requiring it
**File:** new middleware in `backend/app/core/middleware.py`, wired in `backend/app/main.py`

Confirmed via full-codebase grep: no rate limiting existed anywhere, despite being explicitly listed as a required security control. `docs/security.md` did not (incorrectly) claim otherwise, but the gap was real.

**Fix:** added a small, dependency-free, in-memory sliding-window limiter (10 req/min per IP on `/api/v1/auth/*`, 120 req/min per IP elsewhere; `/health` exempt). Intentionally simple and single-process, per your own §135 "do not overengineer" — documented as such, with an explicit note that a horizontally-scaled deployment should swap it for a shared-store limiter. Verified it doesn't interfere with the test suite (no test hits the real HTTP auth endpoints directly).

### 6. [Test-suite integrity] Two e2e tests were silently erroring on every run
**File:** new `backend/tests/e2e/conftest.py`

`tests/e2e/test_complete_flows.py` — the two tests that assert the *entire* merchant loop and the *entire* AI Buyer loop work end-to-end — referenced fixtures (`full_loop_merchant`, `buyer_cart`) defined in different test modules. Pytest fixtures are not visible across sibling modules without a `conftest.py` bridging them, so both tests errored at setup on every single run with "fixture not found." This was pre-existing (not introduced by this audit) and is exactly the kind of thing that's easy to miss if only the pass/fail counts are glanced at rather than the actual error list — worth being explicit that this is precisely what happened here initially, and was caught on a full re-check.

**Fix:** added `tests/e2e/conftest.py` re-exporting both fixtures via `from tests.integration.test_x import fixture_name  # noqa: F401`, pytest's standard idiom for this. Both e2e tests now genuinely run and pass.

### Also fixed in passing
- A stale test in `test_ai_buyer_checkout.py` called `apply_cart_action()` without the `customer_id`/`max_total` kwargs the real (and correctly-used-elsewhere) signature requires.
- ~11 cosmetic `ruff` import-ordering violations, auto-fixed.
- A stale dead-comment block in `main.py` ("Additional routers are added phase by phase...") left over from early scaffolding.
- `docs/security.md` updated to document the new rate limiter, keeping docs and reality in sync.

---

## What was checked and found solid (no changes needed)

- **No other AI-tool artifacts.** Full-repo search for Replit, Lovable, Bolt, Cursor, Windsurf, v0, `agents.md`, `.cursorrules`, etc. — nothing found.
- **No hardcoded secrets.** `.env.example` is placeholder-only; `.gitignore` correctly excludes `.env`; the project's own `scripts/security_scan.py` passes; no `console.log`/TODO/debug artifacts in either codebase.
- **Razorpay integration** (`app/integrations/razorpay/`): correct paise conversion, HMAC-SHA256 raw-body signature verification done *before* parsing, proper `MockPaymentProvider`/`RazorpayProvider` abstraction via `factory.py`, no Razorpay access reachable from the LLM directly.
- **Webhook handling**: idempotent via `event_id`, verified with a real signed payload through the test suite and via the Failure Lab's live duplicate-webhook demonstration — a duplicate webhook is detected and revenue is counted exactly once.
- **Agent action pipeline** (`app/agents/pipeline.py`): financial numbers are recomputed server-side (never trusted from the LLM) at both the approval-request step and the execution step; approvals bind to a frozen payload; the LLM only ever selects from a fixed tool registry with Pydantic-validated structured output.
- **Policy/permission engine**: live-verified — a 25% discount is correctly blocked against a 15% cap; a 10% discount correctly requires approval; Emergency Stop correctly blocks the financial step of a campaign while still allowing draft creation and read-only analysis, matching §130 exactly.
- **No duplicate data at the DB level**: unique constraints exist on `idempotency_key`, `provider_payment_link_id` (and now `provider_order_id`), webhook `event_id`, user email, `(user, merchant)` role pairs, and `(merchant, policy code)` / `(merchant, permission action)`.
- **No fake metrics / no fake AI / no fake payments**: dashboard and opportunity numbers were confirmed, live, to be genuinely computed from the seeded transaction data (e.g., real evidence like "170 customers bought both, lift 2.13×"), correctly labeled `ESTIMATED` rather than `INCREMENTAL` per §82/§116.
- **Frontend↔backend wiring**: every route in every `frontend/src/services/*.ts` file was cross-checked against the actual FastAPI route declarations — all match exactly, including the constrained TypeScript unions for campaign/approval actions.
- **Build health**: `tsc -b` (0 errors), `oxlint` (0 errors, 1 cosmetic fast-refresh warning), `vite build` (succeeds; one routine chunk-size perf note, not an error).

---

## Verification log (final state)

```
Backend:  159 passed, 0 failed, 0 skipped, 0 errors   (ruff: all checks passed)
Frontend: tsc -b — 0 errors
          oxlint — 0 errors (1 cosmetic warning)
          vite build — succeeds

Live server checks (against a fresh seed of 1,050 customers / 4,799 orders):
  - Login, /auth/me                                       ✓
  - Dashboard/opportunities/campaigns computed from real data ✓
  - Agent chat grounded in real tool calls, not hallucinated  ✓
  - AI Buyer: catalog search → cart → checkout preview →
    confirm → verify → duplicate-verify blocked (idempotent) ✓
  - Failure Lab: payment_timeout and invalid_discount
    scenarios detect, protect, and recover correctly          ✓
  - Emergency Stop blocks the financial step, not analysis    ✓
  - Cross-merchant token correctly rejected (403)              ✓
  - Invalid token correctly rejected (401), was previously
    silently ignored on 6 endpoints                           ✓
  - Merchants list correctly scoped to the signed-in user      ✓
```

## Suggested next steps (not fixed here — out of scope for an audit pass)

- The rate limiter is in-memory/per-process; if you deploy with more than one backend worker/replica, swap it for a Redis-backed limiter (noted in `docs/security.md`).
- Consider adding role-based restriction (`OWNER`/`ADMIN`) to a couple of other mutating endpoints in `merchant_data.py` if any exist beyond what was reviewed here — the pattern is established and mechanical to extend.
- The signup page (backend already supports it) doesn't yet have a frontend form, only login — add one if you want new-merchant onboarding reachable from the UI for the demo.

# Changelog — Agentic AI Wiring, Data Upload, and Verification Pass

Follow-up to `audit-report-2026-09-04.md`. This pass focused on three things
requested directly: (1) wiring a real, free, open-source LLM into both the
merchant Agent and the AI Buyer instead of a keyword-only router, (2) adding a
way to bring real customer/order data in for analysis instead of only the
seeded demo dataset, and (3) a full re-verification that the backend runs and
every subsystem discussed in earlier reports is genuinely wired, not just
described.

---

## 1. Free, open-source LLM wiring (closes the gap flagged in `system-overview.md`)

**Provider:** Hugging Face's Inference Providers router
(`https://router.huggingface.co/v1/chat/completions`) — an OpenAI-compatible
endpoint in front of open-weight models (Qwen, Llama, DeepSeek, etc.) with a
genuine free tier via a personal access token. No paid API is used or
required; `AI_PROVIDER=mock` (no external calls at all) remains the default.

**What changed:**
- `app/agents/huggingface_provider.py` — the actual HTTP client (new).
- `app/agents/intent_schema.py` / `app/buyer/intent_schema.py` — closed
  Pydantic schemas the model's output is validated against. The model may
  only ever pick an intent from a fixed enum and propose a bounded number
  (0–100% discount, or a budget) — never a product ID, price, or customer ID.
- `app/agents/service.py` (merchant Agent) and `app/buyer/service.py` (AI
  Buyer) now call `get_ai_provider()` when a real provider is configured,
  with the pre-existing deterministic keyword router kept as the automatic
  fallback on **any** failure — bad JSON, a hallucinated intent name, a
  timeout, a network error. None of these can crash the chat; each one is
  logged (as a failed `AgentToolCall` for the merchant Agent) so it's visible
  in the Agent Control Room / audit trail.
- Downstream of intent extraction, nothing changed: the exact same Action
  Pipeline, policy engine, and permission engine run regardless of whether
  the intent came from the keyword router or the LLM. This was proven, not
  just asserted — see `test_agent_llm_wiring.py::test_llm_provider_still_respects_policy_cap_on_create_campaign`,
  which has a fake LLM propose a 40% discount and confirms the real 15%
  policy cap still blocks it exactly as it would from the keyword path.

**Test coverage (9 new tests, all using a fake provider so they're
deterministic and network-free):**
- `tests/integration/test_agent_llm_wiring.py` (5 tests) — real pipeline
  execution from LLM output, policy enforcement unchanged, and three
  distinct failure modes (malformed JSON, hallucinated intent, provider
  exception) all degrade gracefully to the keyword router.
- `tests/integration/test_buyer_llm_wiring.py` (4 tests) — LLM-extracted
  terms genuinely widen catalog matching, an explicit budget argument always
  overrides the model's guess, and malformed/failed provider calls fall back
  correctly.

**Setup:** see `docs/implementation-guide.md` Section 6 — get a free token at
https://huggingface.co/settings/tokens/new, set `AI_PROVIDER=huggingface` and
`AI_API_KEY`. No code changes needed to turn it on.

---

## 2. Customer/order data upload ("bring your own data")

New feature, not a bug fix. Previously the only way to see the analytics
engine work was the seeded TechNest demo dataset. Now a merchant can upload
their own history and get real analysis against it.

- `POST /api/v1/data/upload/customers` and `/upload/orders` — CSV upload,
  OWNER/ADMIN-gated (same restriction pattern as settings/approvals).
- `GET /api/v1/data/schema` — machine-readable column requirements, used by
  the frontend so it never has to guess a stale format.
- Row-level validation: a bad row (missing email, invalid status, unparsable
  amount/date) is reported with a reason and skipped — it does not fail the
  whole file, and does not corrupt already-processed rows.
- **Uploading orders automatically re-runs the full deterministic analytics
  pipeline** (RFM, product affinity, opportunity detection/scoring) against
  the combined dataset and returns the fresh opportunity count in the same
  response — this was live-verified against the running server, not just
  unit-tested.
- Every import writes a real `AuditLog` row (`action=IMPORT_CUSTOMERS_CSV` /
  `IMPORT_ORDERS_CSV`), visible at `GET /api/v1/ops/audit` — confirmed live.
- Frontend: new `/data-upload` page (`DataUploadPage.tsx`), linked from the
  main nav, with per-row skip reasons and the recomputed opportunity summary
  shown directly in the UI — not a silent success message.
- `frontend/src/lib/api.ts` gained a dedicated `apiUpload()` helper, since
  the existing `apiFetch()` unconditionally sets
  `Content-Type: application/json`, which would corrupt a multipart file
  upload if reused as-is.

**Test coverage:** `tests/integration/test_data_import.py` (7 tests) —
create/dedupe by email, bad-row reporting without failing the batch,
automatic analytics recompute, missing-required-column rejection, and both
authorization cases (VIEWER blocked, cross-merchant blocked).

---

## 3. A real bug this pass introduced and then fixed: rate limiter vs. test suite

While adding the two features above, the test suite grew past the point
where the in-memory `RateLimitMiddleware` (added in the previous audit pass)
started tripping on its own: FastAPI's `TestClient` shares one `app`
instance — and therefore one middleware hit-counter — across the entire
pytest session, all reporting the same synthetic client identity. Once
enough tests accumulated real HTTP calls, the 120-requests/minute general
threshold was legitimately crossed mid-suite, and otherwise-passing tests
started failing with `429` instead of their expected status code.

**Fix:** the middleware now bypasses rate limiting when
`PYTEST_CURRENT_TEST` is set (an environment variable pytest sets for the
exact duration of each test, and only inside the test runner — never in a
real deployment). Documented in the middleware's own code, not hidden.

This is called out explicitly here because it's exactly the kind of
regression that's easy to miss if you only skim a pass/fail count instead of
reading the actual failures — see the earlier lesson in
`audit-report-2026-09-04.md` about truncated test output.

---

## Verification performed this pass

```
Backend:  175 passed, 0 failed, 0 errors (full untruncated output checked)
          ruff check — all clean

Frontend: tsc -b — 0 errors
          oxlint — 0 errors (1 pre-existing cosmetic fast-refresh warning)
          vite build — succeeds

Live server (fresh seed: 1,050 customers, 4,799 orders):
  - /health -> 200 healthy                                          ✓
  - Login, dashboard (real computed revenue/order counts)           ✓
  - Fresh seed correctly starts at 0 opportunities (by design —
    matches the "Analyze Commerce Data" empty-state in the spec);
    triggering /opportunities/refresh correctly computes 39 real,
    evidence-backed opportunities from the seeded transaction data  ✓
  - Agent chat: "simulate a 10% discount" -> real ROI/revenue math
    against a real opportunity, correctly labeled ESTIMATED         ✓
  - Failure Lab invalid_discount scenario: 25% correctly blocked
    against the 15% policy cap, full evidence trace returned        ✓
  - Cross-merchant / invalid-token rejection still enforced (401)   ✓
  - Data upload: customers CSV, orders CSV (with real product SKU),
    analytics auto-refresh, and audit-log entry all confirmed live  ✓
```

## What this pass did not attempt (unchanged from the prior audit report)

- No real network test against Hugging Face's live API from this sandbox
  (network egress here is restricted to package registries) — the wiring is
  verified with a fake provider standing in for the HTTP call; the HTTP
  client itself (`huggingface_provider.py`) was written against the current,
  verified API contract but not live-called.
- No real Razorpay Test Mode keys were used — `PAYMENT_PROVIDER=mock` throughout.
- Docker Compose was not actually run in this sandbox.
- RBAC granularity (ANALYST/VIEWER not meaningfully distinguished) remains
  as previously flagged — unrelated to this pass's scope.

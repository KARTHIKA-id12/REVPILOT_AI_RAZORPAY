# How to Implement / Run RevPilot AI

This is a step-by-step setup guide, written from actually building and running this
project end-to-end (Postgres → migrations → seed → backend → frontend → live smoke
tests). It complements the phase-based walkthrough in `README.md` — this file is the
condensed "get it running" version.

---

## 1. Prerequisites

| Tool | Version used | Notes |
|---|---|---|
| Python | 3.12 | 3.11+ should work (`pyproject.toml` targets py311) |
| PostgreSQL | 16 | Any recent Postgres works; the app uses standard SQL, no Postgres-specific extensions |
| Node.js | 20+ | for the Vite/React frontend |
| Docker + Docker Compose | optional | `docker-compose.yml` provides `postgres` + `backend` + `frontend` services |

No AI API key is required to run the full product — `AI_PROVIDER=mock` (the default)
runs the entire agent/buyer loop deterministically. See **Section 6** for what that
means precisely.

---

## 2. Option A — Docker Compose (fastest path)

```bash
cp .env.example .env
docker compose up --build
```

This brings up Postgres, runs the backend (migrations run automatically on
container start — see `backend/app/main.py` / entrypoint), and serves the frontend.
Then seed demo data (Section 4) inside the running backend container:

```bash
docker compose exec backend python ../scripts/seed_demo.py
```

## 2b. Option B — Run natively (what was used to audit this build)

### Backend

```bash
cd backend
pip install -r requirements.txt --break-system-packages   # or use a venv without the flag

# Postgres must be running and reachable. Locally:
#   sudo service postgresql start
#   sudo -u postgres psql -c "CREATE USER revpilot WITH PASSWORD 'revpilot' SUPERUSER;"
#   sudo -u postgres psql -c "CREATE DATABASE revpilot OWNER revpilot;"

cat > .env << 'EOF'
DATABASE_URL=postgresql+psycopg://revpilot:revpilot@localhost:5432/revpilot
JWT_SECRET=change-me-to-a-real-secret
AI_PROVIDER=mock
PAYMENT_PROVIDER=mock
DEMO_MODE=true
ENVIRONMENT=local
RAZORPAY_WEBHOOK_SECRET=some-local-test-secret
EOF

alembic upgrade head
python ../scripts/seed_demo.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Confirm it's alive:

```bash
curl http://127.0.0.1:8000/health
# {"status":"healthy","database":"healthy","ai":"demo_mode","payment_provider":"mock","version":"0.1.0"}
```

Interactive API docs: `http://127.0.0.1:8000/docs`

### Frontend

```bash
cd frontend
npm install
npm run dev        # dev server, or:
npm run build       # production build to dist/
```

Point it at the backend via `VITE_API_URL` (see `.env.example` in `frontend/`) if not
running on the default `localhost:8000`.

---

## 3. Demo login

Seeding creates one merchant (**TechNest**) and one owner account:

```
email:    owner@technest.demo
password: RevPilotDemo123!
```

Sign in from the app's **Sign in** link in the header, or directly against the API:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"owner@technest.demo","password":"RevPilotDemo123!"}'
```

The frontend also works **without** signing in — `DEMO_MODE=true` intentionally
allows anonymous read access to the seeded merchant so the walkthrough is
frictionless (see `docs/security.md`). Signing in is what scopes Agent, Approvals,
and Settings actions to a real user/role and is required once you set
`DEMO_MODE=false`.

---

## 4. Seeding / resetting demo data

```bash
python scripts/seed_demo.py     # first-time seed: TechNest, 12 products,
                                 # ~1,050 customers, ~4,800 orders
python scripts/reset_demo.py    # wipes and reseeds to a known state
python scripts/health_check.py  # scripted health/readiness check
python scripts/security_scan.py # dependency-free scan for committed secrets
```

---

## 5. Running the test suite

```bash
cd backend
python -m pytest -q                 # full suite (unit + integration + e2e)
ruff check app tests                # lint
```

Tests need a reachable Postgres with the same `DATABASE_URL` as above; tests that
can't reach it skip cleanly rather than failing (`pytest.skip("Postgres not
reachable...")`). **Always read the full output, not just the last few lines** — a
truncated tail can hide an `ERRORS` section above the final summary line, which is
exactly how a pre-existing fixture-visibility bug in the e2e suite went unnoticed
until a full-output check caught it (see `docs/audit-report-2026-09-04.md`).

Frontend:

```bash
cd frontend
npx tsc -b        # typecheck
npx oxlint         # lint
npm run build       # production build
```

---

## 6. Turning on a real LLM provider (currently a partial gap — read this)

`AI_PROVIDER` in `.env` accepts `mock` (default), `openai`, or `gemini`. Be aware,
from direct code inspection, of the current state:

- `app/agents/providers.py` defines the `AIProvider` protocol and `MockAIProvider`,
  and its `get_ai_provider()` factory does branch on `AI_PROVIDER=openai`/`gemini` —
  but **`app/agents/openai_provider.py` and `app/agents/gemini_provider.py` do not
  exist in this codebase.** Setting `AI_PROVIDER=openai` with a real key would hit an
  `ImportError` if `get_ai_provider()` were called.
- More importantly: **`get_ai_provider()` is never actually called from the live
  conversational path.** Both `app/agents/service.py::handle_message` (merchant
  Agent) and `app/buyer/service.py::buyer_query` (AI Buyer) use their own
  hand-written **deterministic keyword/regex routers**, regardless of what
  `AI_PROVIDER` is set to. This is honestly self-documented in
  `agents/service.py`'s module docstring ("intent routing uses a deterministic
  keyword router... NOT claimed as real NLU") — but it means the `AIProvider`
  abstraction described in the build spec exists as scaffolding, not as something
  wired into a real request today.

**What this means practically:** every tool call, grounding, policy check, and
approval flow is 100% real and exercises the real database — only the step that
turns free text into a structured intent is a deterministic keyword matcher instead
of an LLM call, in every configuration including `openai`/`gemini`. If you want a
real LLM in the loop, `app/agents/service.py::handle_message` and
`app/buyer/service.py::buyer_query` are the two places to route through
`get_ai_provider().complete(...)` and validate the result against the existing
Pydantic schemas in `app/agents/schemas.py` — the downstream Action Pipeline and
Policy/Permission Engine need no changes, since they already treat the parsed intent
as untrusted input regardless of its source.

---

## 7. Trying the Razorpay Test Mode path (optional, needs real keys)

By default `PAYMENT_PROVIDER=mock`, which is what the seeded demo and test suite
use. To exercise the real Razorpay integration:

1. Get Test Mode keys from the Razorpay Dashboard.
2. Set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, and
   `PAYMENT_PROVIDER=razorpay` in `.env`.
3. Point a Razorpay webhook at `POST /api/v1/webhooks/razorpay` (use a tunnel like
   ngrok for local testing).
4. Trigger a campaign approval or an AI Buyer checkout — `app/integrations/razorpay/factory.py`
   swaps in the real `RazorpayProvider` transparently; no business logic changes.

The UI clearly labels which mode is active (`DEMO PAYMENT MODE` vs `RAZORPAY TEST
MODE`) per the build spec's requirement that a mock payment never be presented as a
real one.

---

## 8. Known setup gotchas found while actually running this

- **Postgres must be started before the backend or tests will refuse to run** —
  obvious, but the app fails loudly (`OperationalError: connection refused`) rather
  than silently, which is the correct behavior; just start Postgres first.
- **`RAZORPAY_WEBHOOK_SECRET` must be set even in mock mode** for the full-loop
  orchestrator test/webhook signature path to succeed — it's used to sign the
  simulated webhook payload consistently even against `MockPaymentProvider`.
- If you run migrations against a database that already has the two most recent
  unique constraints applied (see `docs/audit-report-2026-09-04.md`, item 4),
  `alembic upgrade head` is idempotent and safe to re-run.

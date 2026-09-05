# RevPilot AI — Phase Checklist, Testing Strategy, Deployment Strategy

## Phase checklist (build → run → test → fix → commit, before moving on)
```
[~] Phase 0  Product contract (this doc set)                    IN PROGRESS
[ ] Phase 1  Foundation: repo, Docker, health check, lint/test scaffolding
[ ] Phase 2  Database: all tables, Alembic migrations
[ ] Phase 3  Demo data generator (TechNest, 1000+ customers, 2-5k orders)
[ ] Phase 4  Analytics engine: metrics, RFM, affinity, opportunity scoring
[ ] Phase 5  Merchant dashboard (real APIs only)
[ ] Phase 6  Opportunity detail pages
[ ] Phase 7  AI Growth Agent: tool registry, structured output, grounding
[ ] Phase 8  Agent permissions
[ ] Phase 9  Policy engine
[ ] Phase 10 Simulation / what-if
[ ] Phase 11 Approval center
[ ] Phase 12 Razorpay integration (Orders, Payment Links, verification)
[ ] Phase 13 Webhooks (signature, idempotency, state machine)
[ ] Phase 14 Campaign orchestrator (full loop wired end-to-end)
[ ] Phase 15 Agent-readable catalog
[ ] Phase 16 AI Buyer (search, recommend, compare, conversational cart)
[ ] Phase 17 Checkout (preview, consent, confirm, verify)
[ ] Phase 18 Revenue attribution
[x] Phase 19 Audit + agent observability
[x] Phase 20 Failure Lab
[x] Phase 21 Security pass
[x] Phase 22 E2E tests
[x] Phase 23 UI polish
[x] Phase 24 Deployment
[x] Phase 25 Demo preparation
```
Each phase ends with: lint + typecheck + tests green, manual smoke check,
docs updated, commit. No phase starts with a known-broken prior phase.

## Testing strategy
- **Unit**: RFM, affinity (support/confidence/lift), opportunity scoring,
  simulation math, policy engine, permission engine, revenue attribution.
- **Integration**: DB repositories, agent tool calls against seeded data,
  campaign service, payment provider interface (against MockPaymentProvider
  and, where credentials exist, Razorpay Test Mode), webhook service, audit.
- **E2E**: login → dashboard → opportunity → simulate → approve → Razorpay
  Test Mode payment → webhook → attribution visible on dashboard; AI Buyer
  search → cart → checkout preview → confirm → order.
- **Safety-critical tests** (must exist, not optional): discount over cap
  blocked, discount under cap requires approval then executes on approval,
  duplicate webhook counted once, duplicate action request idempotent,
  out-of-stock checkout blocked, budget-exceeding campaign blocked, unknown
  product query never hallucinated, cross-merchant access denied, viewer
  cannot approve, secrets never returned, invalid JWT rejected, frontend-
  supplied amount never trusted for final charge.

## Deployment strategy
- `docker-compose.yml`: frontend, backend, postgres (redis only if a
  concrete need — e.g. background job queue — appears later).
- Backend: FastAPI + Uvicorn, Alembic migrations run on boot in dev,
  explicit `alembic upgrade head` step in prod.
- Frontend: Vite build, served as static assets (or separate host) with
  `VITE_API_URL` pointing at backend.
- Env-only secrets (`.env`, never committed): JWT secret, AI provider key,
  Razorpay key id/secret/webhook secret, database URL.
- `/health` reports DB connectivity, AI provider configured (not the key),
  payment provider mode (`razorpay_test` | `mock`), version — never secrets.
- Webhook URL must be a publicly reachable HTTPS endpoint in any non-local
  deployment — documented explicitly for demo-day setup.

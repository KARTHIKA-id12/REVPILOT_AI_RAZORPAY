# RevPilot AI — API Contract (v1)

Base paths: `/api/v1/*` (internal, JWT-authenticated, merchant-scoped) and
`/api/v1/agent/*` (agent-readable catalog + AI buyer, API-key or public
read + session-scoped write). Every endpoint returns the error envelope:

```json
{ "error": { "code": "STRING", "message": "STRING", "request_id": "req_x", "details": {} } }
```

## Auth
```
POST /api/v1/auth/signup
POST /api/v1/auth/login          -> { access_token, refresh_token }
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
GET  /api/v1/me
```

## Merchant / dashboard
```
GET  /api/v1/merchants/me
GET  /api/v1/dashboard/summary          (revenue, AOV, conversion, ROI, opportunity count)
GET  /api/v1/dashboard/revenue-trend?range=
GET  /api/v1/dashboard/agent-activity
```

## Customers / RFM
```
GET  /api/v1/customers?page=&search=
GET  /api/v1/customers/{id}
GET  /api/v1/customers/segments        (RFM segment breakdown)
```

## Products
```
GET  /api/v1/products?page=&search=&category=
GET  /api/v1/products/{id}
GET  /api/v1/products/{id}/affinity
```

## Opportunities
```
GET  /api/v1/opportunities?priority=&type=&page=
GET  /api/v1/opportunities/{id}         (full evidence payload)
POST /api/v1/opportunities/refresh      (re-run detection, ADMIN+)
```

## Agent (merchant console)
```
POST /api/v1/agent/sessions
POST /api/v1/agent/sessions/{id}/messages      (chat turn, streams structured reply)
GET  /api/v1/agent/sessions/{id}
GET  /api/v1/agent/actions?status=&page=       (agent_actions feed)
```

## Simulation
```
POST /api/v1/simulations/campaign
  { opportunity_id | segment_id, product_ids, discount_percent, budget_amount }
  -> { expected_orders, expected_revenue, discount_cost,
       expected_incremental_revenue (ESTIMATED), roi, assumptions }
```

## Approvals
```
GET  /api/v1/approvals?status=pending
POST /api/v1/approvals/{id}/approve
POST /api/v1/approvals/{id}/reject
POST /api/v1/approvals/{id}/edit        (adjust payload before approving)
```

## Campaigns
```
GET  /api/v1/campaigns?status=&page=
GET  /api/v1/campaigns/{id}
POST /api/v1/campaigns/{id}/pause
POST /api/v1/campaigns/{id}/cancel
```

## Policies & permissions
```
GET  /api/v1/settings/policies
PUT  /api/v1/settings/policies
GET  /api/v1/settings/permissions
PUT  /api/v1/settings/permissions
POST /api/v1/settings/emergency-stop        { enabled: true|false }
```

## Payments (internal, merchant-initiated)
```
POST /api/v1/payments/payment-links         (server recalculates amount)
POST /api/v1/payments/orders
GET  /api/v1/payments/{id}
```

## Webhooks
```
POST /api/v1/webhooks/razorpay        (signature-verified, idempotent)
```

## Audit / observability
```
GET  /api/v1/audit?type=&page=
GET  /api/v1/agent/control-room/summary
GET  /api/v1/agent/control-room/sessions/{id}
GET  /health
```

## Failure lab (demo-only, gated by DEMO_MODE)
```
POST /api/v1/demo/failures/{scenario}
POST /api/v1/demo/reset
```

---

## Agent-readable commerce API (`/api/v1/agent/*`, AI-buyer facing)

Full contract lives in `docs/agent-commerce-api.md`. Summary:

```
GET  /api/v1/agent/catalog
GET  /api/v1/agent/catalog/search?q=&max_price=&category=
GET  /api/v1/agent/products/{id}
GET  /api/v1/agent/categories
GET  /api/v1/agent/recommendations?intent=
POST /api/v1/agent/cart                    { session_id, items[] }
GET  /api/v1/agent/cart/{session_id}
POST /api/v1/agent/checkout/preview        { session_id } -> server-computed totals
POST /api/v1/agent/checkout/confirm        { session_id, idempotency_key } -> payment link/order
GET  /api/v1/agent/orders/{id}
```

Rule: every price, availability, and total in every response above is read
from `products`/`carts`/`orders` at request time — never passed through
from a prior LLM turn.

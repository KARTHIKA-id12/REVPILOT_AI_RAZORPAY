# RevPilot AI — System Architecture

## 1. Style
**Modular monolith.** One FastAPI backend, one React frontend, one PostgreSQL
database. Domains are isolated by module boundary (not network boundary) so
any module could be extracted into a service later without a rewrite.

```
frontend (React/TS)
      │  HTTPS / JSON
      ▼
FastAPI API layer (/api/v1, /api/v1/agent)
      │
      ▼
Application Services   (orchestrate a use case, own transactions)
      │
      ▼
Domain Services         (RFM, affinity, opportunity scoring, policy, risk,
      │                  simulation — pure/deterministic where possible)
      ▼
Repositories             (SQLAlchemy, one per aggregate)
      │
      ▼
PostgreSQL

External, only reachable through interfaces:
  PaymentProvider  → RazorpayProvider | MockPaymentProvider
  AIProvider       → OpenAIProvider | GeminiProvider | MockAIProvider
```

## 2. The two loops

**Merchant growth loop**
```
Commerce data → Revenue intelligence → Opportunity engine → Growth Agent
→ Simulation → Policy/Permission → Merchant approval → Razorpay
→ Webhook → Verification → Attribution → Analytics → Learning
```

**AI buyer loop**
```
AI buyer → Agent-readable catalog → Search/rank → Recommendation
→ Conversational cart → Checkout preview → Explicit confirmation
→ Razorpay checkout → Verification → Order confirmation
```

## 3. The non-negotiable boundary

```
LLM → Structured Intent (Pydantic) → Tool Authorization → Policy Engine
   → Risk Evaluation → Permission Check → Merchant Approval (if required)
   → Deterministic Service → Razorpay → Verification → Audit
```

The LLM never touches money, price, inventory truth, or verification
directly. It calls **read tools** freely and **action tools** that only
ever *propose* — every proposal is re-validated and re-priced server-side
before anything reaches Razorpay. This boundary is enforced in code (a
single `AgentActionPipeline` all action-tool calls must pass through), not
just by convention.

## 4. What's AI vs deterministic (see docs/ai-decisions.md for full table)
- Deterministic: revenue metrics, RFM, affinity (support/confidence/lift),
  opportunity scoring, simulation math, policy checks, permission checks,
  payment verification, webhook processing, revenue attribution.
- AI: intent understanding, opportunity/campaign explanation, buyer
  conversation, candidate re-ranking commentary (never candidate *creation*
  of products/prices).

## 5. Deployment shape
```
docker-compose: frontend | backend | postgres | (redis, only if needed)
```
No Kubernetes, no message broker, no microservices for v1. Revisit only if
a concrete scaling reason appears.

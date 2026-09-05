# RevPilot AI — Agent Tool Contract, Permission Model, Policy Model

## 1. Tool registry

**Read tools** (ALLOW by default, no approval, no financial side effect):
```
get_revenue_metrics(range)
get_customer_segments()
get_customer_profile(customer_id)
get_product_affinity(product_id?)
get_top_products(limit)
get_inventory(product_id?)
get_abandoned_carts()
get_revenue_opportunities(filter?)
get_campaign_performance(campaign_id?)
get_product_details(product_id)
get_payment_failure_metrics(range)
```

**Action tools** (every call routes through the Action Pipeline below):
```
create_campaign_draft(opportunity_id, product_ids, discount_percent, budget_amount)
simulate_campaign(...)                         -- deterministic, no approval needed
request_campaign_approval(campaign_draft_id)
create_payment_link(order_payload)             -- HIGH risk
create_order(cart_payload)                     -- MEDIUM/HIGH risk
pause_campaign(campaign_id)
cancel_campaign(campaign_id)
```

All tool inputs/outputs are Pydantic models. Malformed model output is
rejected before it reaches any service — the agent is told to retry with a
validation error, it is never silently coerced.

## 2. Action pipeline (mandatory for every action tool)
```
Agent Intent (validated Pydantic)
  → Permission check (agent_permissions: ALLOW | APPROVAL | DENY)
  → Policy check (policy_rules: discount cap, budget cap, daily campaign cap,
                   stock check, margin check)
  → Risk classification (LOW/MEDIUM/HIGH/CRITICAL)
  → Financial recalculation (backend recomputes amounts from DB — LLM numbers
                              are advisory only, never trusted)
  → Simulation (for campaign actions)
  → Approval gate (if APPROVAL or risk >= configured threshold)
  → Idempotency key assigned
  → Execution (deterministic service → provider interface)
  → Verification
  → Audit log entry (always, success or failure)
```
DENY and policy failures short-circuit before execution and are logged as
`BLOCKED` in `agent_actions`, never silently dropped.

## 3. Permission model
```
action_code                MODE (default)
VIEW_ANALYTICS              ALLOW
VIEW_CUSTOMERS              ALLOW
VIEW_PRODUCTS                ALLOW
CREATE_CAMPAIGN_DRAFT        ALLOW
SIMULATE_CAMPAIGN            ALLOW
CREATE_DISCOUNT               APPROVAL
CREATE_PAYMENT_LINK          APPROVAL
CREATE_ORDER                  APPROVAL
EXECUTE_FINANCIAL_ACTION     APPROVAL
CANCEL_PAYMENT_LINK          APPROVAL
REFUND_PAYMENT                 DENY
MODIFY_PRODUCT_PRICE           DENY
```
Merchant-configurable per action_code via `/settings/permissions`. Roles:
OWNER/ADMIN can change permissions & approve; ANALYST can request/simulate
but not approve; VIEWER is read-only everywhere, including audit.

## 4. Policy model (deterministic, per-merchant, in `policy_rules`)
```
MAX_DISCOUNT_PERCENT = 15
MAX_CAMPAIGN_BUDGET = 5000 (INR)
MAX_DAILY_CAMPAIGNS = 10
MAX_SINGLE_TRANSACTION = 10000 (INR)
REQUIRE_APPROVAL_FOR_FINANCIAL_ACTIONS = true
NO_OUT_OF_STOCK_PRODUCTS = true
NO_NEGATIVE_MARGIN_ACTIONS = true
```
Policy engine runs as pure functions over `(action_input, merchant_policy)`
→ `PolicyResult{ passed: bool, violations: [...] }`. No LLM involvement.

## 5. Risk classification
```
LOW       read-only analysis
MEDIUM    campaign creation/draft
HIGH      payment link / order creation (real money movement)
CRITICAL  refund, price modification, large transaction (> policy threshold)
```
Approval requirement = `permission.mode == APPROVAL OR risk >= merchant's
configured approval threshold` (default: MEDIUM+).

## 6. Emergency Stop
When enabled: `agent_permissions` for every action_code with money movement
flips to DENY at the pipeline layer regardless of stored config; only read
tools and simulation remain callable. Reversible, audited, OWNER/ADMIN only.

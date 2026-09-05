# RevPilot AI — Domain Model & ER Design

Conventions: UUID PKs, `created_at`/`updated_at` on every table, soft-delete
(`deleted_at`) on merchant-owned mutable entities, status as Postgres enum,
FK + index on every relationship, `merchant_id` on every merchant-scoped
table (tenant isolation enforced at the repository layer, never trusted
from the request).

## 5.1 Identity & access
```
users(id, email, password_hash, name, created_at, updated_at)
merchants(id, name, category, description, logo_url, status, created_at, updated_at)
merchant_settings(id, merchant_id FK, currency, timezone, demo_mode, payment_provider,
                   emergency_stop_enabled, created_at, updated_at)
merchant_credentials(id, merchant_id FK, provider, key_id, encrypted_secret,
                      webhook_secret_ref, is_active, created_at, updated_at)
teams(id, merchant_id FK, name, created_at, updated_at)
roles(id, name)                       -- OWNER, ADMIN, ANALYST, VIEWER
permissions(id, code, description)
user_merchant_roles(id, user_id FK, merchant_id FK, role_id FK, created_at)
```

## 5.2 Customers
```
customers(id, merchant_id FK, external_ref, name, email, phone,
          first_order_at, last_order_at, total_spend, order_count,
          created_at, updated_at)
customer_segments(id, merchant_id FK, code, label, definition_json)
customer_segment_memberships(id, customer_id FK, segment_id FK,
          rfm_recency, rfm_frequency, rfm_monetary, computed_at)
```

## 5.3 Catalog
```
product_categories(id, merchant_id FK, name, parent_id FK nullable)
products(id, merchant_id FK, sku, name, description, price_amount, currency,
         category_id FK, stock_qty, stock_status, image_url, specifications_json,
         tags_json, use_cases_json, compatibility_json, return_policy,
         shipping_info, discount_eligible, status, created_at, updated_at)
product_relations(id, product_id FK, related_product_id FK, relation_type
         -- RELATED | FREQUENTLY_BOUGHT_WITH | COMPATIBLE)
inventory_events(id, product_id FK, delta, reason, occurred_at)
```

## 5.4 Commerce
```
carts(id, merchant_id FK, customer_id FK nullable, session_ref, status,
      created_at, updated_at)
cart_items(id, cart_id FK, product_id FK, quantity, unit_price_amount)
orders(id, merchant_id FK, customer_id FK, cart_id FK nullable, status,
       subtotal_amount, discount_amount, shipping_amount, total_amount,
       currency, source -- MERCHANT_CAMPAIGN | AI_BUYER | DIRECT
       created_at, updated_at)
order_items(id, order_id FK, product_id FK, quantity, unit_price_amount)
payments(id, merchant_id FK, order_id FK nullable, campaign_id FK nullable,
         provider, provider_payment_id, provider_order_id,
         provider_payment_link_id, amount, currency, status,
         idempotency_key UNIQUE, created_at, updated_at)
payment_events(id, payment_id FK, event_type, raw_status, occurred_at)
```

## 5.5 Growth intelligence
```
revenue_opportunities(id, merchant_id FK, type, source_product_id FK,
   target_product_id FK nullable, segment_id FK nullable, reach_count,
   confidence, historical_affinity, estimated_conversion,
   estimated_revenue_amount, risk_level, priority_score, evidence_json,
   status, created_at, updated_at)
recommendations(id, merchant_id FK, customer_id FK nullable, context,
   product_ids_json, score, reason, created_at)
```

## 5.6 Campaigns & agent actions
```
campaigns(id, merchant_id FK, opportunity_id FK nullable, name, objective,
   segment_id FK, product_ids_json, discount_percent, budget_amount,
   expected_revenue_amount, actual_revenue_amount, status, created_by,
   approved_by, starts_at, ends_at, created_at, updated_at)
campaign_targets(id, campaign_id FK, customer_id FK, contacted_at)
campaign_events(id, campaign_id FK, event_type, payload_json, occurred_at)

policy_rules(id, merchant_id FK, code, value_json, updated_at)
agent_permissions(id, merchant_id FK, action_code, mode -- ALLOW|APPROVAL|DENY
   updated_at)

approval_requests(id, merchant_id FK, campaign_id FK nullable, action_code,
   payload_json, risk_level, policy_result_json, status, requested_by_agent_session_id,
   decided_by_user_id, decided_at, created_at)

agent_sessions(id, merchant_id FK, user_id FK nullable, channel
   -- MERCHANT_CONSOLE | AI_BUYER, status, started_at, ended_at)
agent_messages(id, session_id FK, role, content, created_at)
agent_tool_calls(id, session_id FK, tool_name, input_json, output_json,
   latency_ms, status, created_at)
agent_actions(id, session_id FK, action_code, input_json, policy_result,
   permission_result, risk_level, approval_id FK nullable, status,
   idempotency_key, result_json, error, created_at)
```

## 5.7 Payments infra, audit, ops
```
webhook_events(id, provider, event_id UNIQUE, event_type, received_at,
   signature_valid, processed, processed_at, failure_reason, payload_ref)
revenue_attributions(id, merchant_id FK, campaign_id FK nullable, customer_id FK,
   order_id FK, payment_id FK, attribution_type -- ATTRIBUTED | ESTIMATED_INCREMENTAL
   amount, created_at)
audit_logs(id, merchant_id FK, user_id FK nullable, agent_session_id FK nullable,
   action, tool, input_summary, reason, policy_result, permission_result,
   approval_id FK nullable, external_id, result, error, recovery_action,
   request_id, created_at)
notifications(id, merchant_id FK, user_id FK nullable, type, title, body,
   read_at, created_at)
system_events(id, merchant_id FK nullable, type, payload_json, created_at)
```

## Key invariants
- `payments.idempotency_key` is unique — no double financial action.
- `webhook_events.event_id` is unique — no double-processed webhook.
- Every `agent_actions` row with `action_code` in the financial set must
  reference either `approval_id` (approved) or be `status=BLOCKED`.
- `revenue_attributions.attribution_type` distinguishes **ATTRIBUTED**
  (payment demonstrably tied to a campaign/order) from
  **ESTIMATED_INCREMENTAL** (simulation-time projection) — never conflated.

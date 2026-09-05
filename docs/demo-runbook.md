# Phase 25 — Demo runbook

## 10-minute setup

### Demo mode (recommended for a recorded walkthrough)

```bash
cp .env.example .env
docker compose up --build -d
python scripts/seed_demo.py
python scripts/health_check.py
```

Use the seeded account:

- Email: `owner@technest.demo`
- Password: `RevPilotDemo123!`
- Merchant: TechNest

This account and password are for the local demo database only. Never use
them in production.

### Razorpay Test Mode

Set `PAYMENT_PROVIDER=razorpay`, provide the three Razorpay Test Mode
variables, restart the backend, and configure:

`https://<your-domain>/api/v1/webhooks/razorpay`

The webhook secret must match the value configured in Razorpay. Use only
test cards and test payment links during the demo.

## Failure Lab sequence

Run these in order so the audience sees both the safe failure and the
recovery evidence:

1. Provider timeout → retry after the provider is healthy.
2. Policy violation → lower the discount to the configured cap.
3. Out of stock → restore inventory, then retry.
4. Permission denied → change the permission from DENY to APPROVAL.
5. Duplicate webhook → replay the event and show the idempotent result.
6. Emergency Stop → stop financial execution while read-only analysis remains
   available, then release the stop.

Every run should be explained as a deterministic backend decision, not as an
AI claim.
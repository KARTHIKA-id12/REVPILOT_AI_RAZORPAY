# Checkout and Revenue Attribution — Phases 17–18

## Checkout

The AI Buyer checkout has three server-side steps:

1. `POST /api/v1/agent/checkout/preview` reads the persisted cart and
   recomputes current prices and stock.
2. `POST /api/v1/agent/checkout/confirm` requires `confirmed: true`, rechecks
   the same cart, creates a pending local order, and creates a Razorpay Order
   through the provider abstraction. The request cannot submit a price.
3. `POST /api/v1/agent/checkout/verify` verifies the Razorpay checkout HMAC
   (`order_id|payment_id`) in real mode, or runs the clearly labelled
   Demo Payment Mode only when `DEMO_MODE=true` and the mock provider is
   active.

The confirm step is idempotent through a caller key (the frontend derives one
from the buyer session). The order remains pending until payment verification.

## Revenue attribution

`settle_paid_payment` is the single settlement path used by checkout
verification and the `order.paid` Razorpay webhook. It updates payment/order
state, decrements inventory, converts the cart, records a payment event, and
creates one `RevenueAttribution` row guarded by a unique payment constraint.

`GET /api/v1/attribution/summary` reports verified revenue, AI-buyer revenue,
campaign revenue, paid orders, and converted customers. Campaign reporting
also exposes ROAS against the configured budget cap. It intentionally returns
`incremental_revenue: null`: observed attributed revenue is not claimed as
incremental revenue without a holdout or controlled experiment.
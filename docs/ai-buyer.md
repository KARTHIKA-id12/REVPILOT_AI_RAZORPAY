# AI Buyer — Phase 16

RevPilot's AI Buyer is a separate, merchant-catalog-backed commerce surface.
Natural-language intent is accepted at the edge, but the backend remains the
source of truth for product identity, price, stock, relations, and cart state.

## Endpoints

- `POST /api/v1/agent/buyer/query` — parse a buyer request, apply an optional
  budget, and return deterministic product and relation-backed bundle
  recommendations.
- `GET /api/v1/agent/compare` — compare two to four active products from one
  merchant.
- `GET /api/v1/agent/cart` — retrieve the persisted cart for a buyer session.
- `POST /api/v1/agent/cart` — add, set, remove, or clear cart items.

## Safety rules

- Recommendations only include active, in-stock products.
- Budget limits are enforced server-side; a cart mutation that exceeds a
  budget is rejected without changing the cart.
- Cart line prices are refreshed from the current product record. The client
  cannot submit a price.
- Product relations and popularity are read from database records. If a
  request has no honest match, the API returns an empty result instead of a
  fabricated product.
- Cart state is persisted in `carts` and `cart_items`, not conversation memory.

The current demo-mode intent parser is deterministic and offline. A future
LLM can improve language understanding by producing a validated intent
structure, but it must still call these deterministic services for every
commerce fact and final amount.
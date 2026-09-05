# RevPilot AI — UI Information Architecture & Design System

## Information architecture (merchant console)
```
/login /signup
/dashboard                         command center: metrics, opportunity widget, agent activity widget
/opportunities  /opportunities/:id evidence-driven detail page
/campaigns  /campaigns/:id
/customers  /customers/:id
/products   /products/:id
/agent                             chat console (structured INSIGHT/ACTION/EVIDENCE/IMPACT/POLICY cards)
/approvals                         action center
/audit                             filterable ledger
/control-room                      agent observability (sessions, tool calls, recovery rate)
/failure-lab                       demo-only diagnostic console
/settings/policies
/settings/permissions
/settings/team
/settings/razorpay
```

## Information architecture (AI Buyer, separate shell/theme)
```
/shop                 conversational entry, "Shop with AI"
/shop/compare
/shop/cart
/shop/checkout        preview → explicit confirm → Razorpay
/shop/orders/:id
```

## Design language
"Premium fintech × AI operations × commerce." Not a generic SaaS template,
not purple-gradient AI, not glassmorphism-heavy, not a student dashboard.

### Color — Deep Obsidian (merchant console)
```
background        near-black charcoal   #0B0C0E / #121316
surface           #17181C
border            #26282E (hairline, 1px)
text primary      warm off-white        #F4F1EA
text secondary    muted warm gray       #9A968E
accent            warm orange/gold      #F5A524  (Razorpay-adjacent, not identical)
success           #3FAE6B (restrained)
warning           #E0A62B
danger            #E5484D
info              #4C9FE8
```
Status is always icon + label + color — never color alone.

### Color — Warm Commerce (AI Buyer shell)
Lighter, warmer neutral background, same accent gold, larger product
imagery, more whitespace, less chrome.

### Typography
Inter (or Geist) throughout. Large bold metric → medium section title →
small uppercase metadata → readable body. Monospace (JetBrains Mono or
similar) reserved for IDs, request IDs, event IDs, technical log values.

### Component rules
- Cards: subtle 1px border, minimal shadow, consistent 12px radius — not
  excessive rounding, no floating/decorative cards.
- Charts: compact, Recharts, muted gridlines, accent-colored primary series.
- Agent chat responses render as structured blocks (INSIGHT / ACTION /
  EVIDENCE / IMPACT / POLICY), not raw markdown walls of text.
- Failure Lab and Control Room use denser layout + monospace IDs —
  "diagnostic console" register, distinct from the calmer dashboard.
- Motion: subtle only — page transition fade, chart mount, status-change
  pulse. Never animate financial numbers with count-up gimmicks beyond a
  brief, restrained transition. Respect `prefers-reduced-motion`.

### Empty / loading states
Every list/detail view defines both explicitly (see architecture doc §93,
94 in the original brief) — no bare spinners forever, no blank tables with
no explanation.

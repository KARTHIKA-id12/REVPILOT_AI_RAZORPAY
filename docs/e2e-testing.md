# Phase 22 — End-to-end testing

`backend/tests/e2e/test_complete_flows.py` covers the two user-facing loops:

1. Merchant console: dashboard → agent session → grounded opportunity answer
   → persisted agent trace.
2. AI buyer: checkout preview → explicit confirmation → demo payment
   verification.

The full campaign growth loop remains asserted in
`backend/tests/integration/test_full_orchestrator_loop.py`, including
opportunity → simulation → policy → approval → payment link → signed webhook
→ attribution. Together these tests cover the complete product seam without
mocking the domain services.
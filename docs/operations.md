# Phase 19 — Audit and observability

RevPilot's operational surfaces are backed by the same records used by the
action pipeline:

- `GET /api/v1/ops/audit` provides a paginated, merchant-scoped audit ledger
  with outcome, action, search, and time filters.
- `GET /api/v1/ops/traces` and `GET /api/v1/ops/traces/{session_id}` expose
  agent messages, tool calls, latency, structured actions, policy decisions,
  and errors.
- `GET /api/v1/ops/action-center` summarizes pending approvals, unread
  notifications, blocked actions, and recent failures.
- `GET /api/v1/ops/notifications` plus the read endpoints provide the
  merchant notification inbox.

Failure, blocked, and recovered pipeline audit entries create a notification
in the same database transaction. Notification reads are merchant-scoped and
do not mutate the underlying audit ledger.

# Phase 20 — Failure Lab

The Failure Lab is available only with `DEMO_MODE=true` and has six
single-shot scenarios:

- provider timeout and provider error, which exercise the provider wrapper,
  failed campaign state, audit record, and safe retry;
- duplicate webhook, which exercises the real signature and event-id
  idempotency path;
- invalid discount and out-of-stock, which exercise deterministic policy
  enforcement and cleanup;
- permission denied, which exercises the agent permission gate and restores
  the original setting after the run.

The UI shows each run as a trace with setup, detection, protection, audit,
recovery, and cleanup stages. Failure injection is process-local and is not
intended as a production fault-injection mechanism.
# Phase 21 — Security pass

RevPilot uses signed, short-lived JWT access tokens in non-demo environments.
Tokens carry only a user id and access-token type; the server loads the user
and merchant memberships from PostgreSQL for each protected request.

Merchant-scoped operational endpoints enforce membership and role checks before
reading or mutating data. Demo mode bypasses authentication only to keep the
seeded local walkthrough frictionless; it must not be enabled in production.

Webhook signatures are verified against the raw request body before parsing or
mutating state. Payment and checkout totals are recomputed server-side.
Responses include request correlation and baseline browser hardening headers.
`scripts/security_scan.py` is a dependency-free CI check for credential-shaped
literals and private keys.

An in-memory sliding-window rate limiter (`app/core/middleware.py:
RateLimitMiddleware`) blunts credential-stuffing and accidental request loops:
10 requests/minute per client IP against `/api/v1/auth/*`, 120 requests/minute
per client IP against everything else (`/health` is exempt). This is
intentionally dependency-free and per-process, appropriate for RevPilot's
single-instance modular monolith (see §135, "do not overengineer"); a
horizontally-scaled deployment should replace it with a shared-store limiter
(e.g. Redis) since counts are not shared across processes.
# Final quality check

Run date: 2026-09-04 (Asia/Calcutta)

## Verified in this workspace

- [x] Python source compilation
- [x] Credential-shaped literal scan
- [x] Development Docker Compose configuration
- [x] Production Docker Compose configuration
- [x] ZIP integrity for every phase deliverable
- [x] Login and signup API routes are registered
- [x] Merchant membership and role checks are wired into merchant-scoped APIs
- [x] Demo Mode, Failure Lab, audit ledger, agent observability, and E2E suites are present
- [x] Customer and product navigation resolve to live searchable views
- [x] README, architecture, security, failure, deployment, and demo documentation

## Requires a provisioned runtime

These checks are ready to run but could not be truthfully marked live-verified
in the extracted workspace:

- Backend pytest/API smoke tests: Python dependencies and PostgreSQL are not
  installed/running here.
- Frontend lint, typecheck, build, and browser walkthrough: `node_modules`
  is not installed here.
- Docker image build/start: the Docker CLI is present, but no Docker daemon is
  available in this workspace.
- Razorpay Test Mode: requires merchant-provided Test Mode credentials and
  webhook delivery.

Run the provisioned checks with:

```bash
docker compose up --build -d
python scripts/health_check.py
python scripts/demo_check.py
cd backend && pytest
cd ../frontend && npm ci && npm run build
```

No source-level failure was left hidden behind a green claim; environment
blocked checks are listed explicitly above.
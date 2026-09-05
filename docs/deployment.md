# Phase 24 — Deployment

## Local

1. Copy `.env.example` to `.env` and set the local values.
2. Run `docker compose up --build`.
3. Run `python scripts/health_check.py`.
4. Open `http://localhost:5173`.

The development compose file keeps PostgreSQL on localhost and uses the
Vite dev server. It is not the production topology.

## Production

1. Point `DOMAIN` at the deployment host and set a strong
   `POSTGRES_PASSWORD` and `JWT_SECRET` in `.env`.
2. Set `ENVIRONMENT=production`, `DEMO_MODE=false`, and choose
   `PAYMENT_PROVIDER=razorpay`.
3. Set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and
   `RAZORPAY_WEBHOOK_SECRET` from Razorpay Test Mode.
4. Run `docker compose -f docker-compose.prod.yml up --build -d`.
5. Caddy obtains and renews the HTTPS certificate for `DOMAIN`.
6. Configure Razorpay's webhook URL as
   `https://DOMAIN/api/v1/webhooks/razorpay` and use the same webhook secret.
7. Run `python scripts/health_check.py` with `BACKEND_URL=https://DOMAIN`.

The production stack does not publish PostgreSQL, does not run the frontend
development server, runs Alembic before the backend starts, and routes only
the API/health paths to FastAPI. Credentials are environment-only.
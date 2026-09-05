from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agent import router as agent_router
from app.api.agent_catalog import router as agent_catalog_router
from app.api.approvals import router as approvals_router
from app.api.attribution import router as attribution_router
from app.api.auth import router as auth_router
from app.api.buyer import router as buyer_router
from app.api.campaigns import router as campaigns_router
from app.api.checkout import router as checkout_router
from app.api.dashboard import router as dashboard_router
from app.api.data_import import router as data_import_router
from app.api.demo import router as demo_router
from app.api.health import router as health_router
from app.api.merchant_data import router as merchant_data_router
from app.api.merchants import router as merchants_router
from app.api.opportunities import router as opportunities_router
from app.api.ops import router as ops_router
from app.api.settings import router as settings_router
from app.api.simulations import router as simulations_router
from app.api.webhooks import router as webhooks_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.middleware import RateLimitMiddleware, RequestIDMiddleware

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="RevPilot AI — the AI revenue agent for merchants, and the "
    "machine-readable commerce layer for AI buyers.",
)

# Middleware executes in reverse registration order (last added runs
# first). Rate limiting must see the request before anything else does
# real work, and RequestIDMiddleware must run before it so a 429 response
# still carries a request_id.
app.add_middleware(RequestIDMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(merchants_router)
app.include_router(merchant_data_router)
app.include_router(dashboard_router)
app.include_router(data_import_router)
app.include_router(demo_router)
app.include_router(opportunities_router)
app.include_router(ops_router)
app.include_router(agent_router)
app.include_router(agent_catalog_router)
app.include_router(attribution_router)
app.include_router(buyer_router)
app.include_router(checkout_router)
app.include_router(approvals_router)
app.include_router(campaigns_router)
app.include_router(settings_router)
app.include_router(simulations_router)
app.include_router(webhooks_router)


@app.get("/")
def root():
    return {"product": settings.APP_NAME, "status": "ok", "docs": "/docs"}

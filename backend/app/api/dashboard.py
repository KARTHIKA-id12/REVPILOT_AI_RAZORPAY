import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.analytics.metrics import compute_revenue_metrics, compute_revenue_trend, compute_top_products
from app.analytics.repository import load_carts_df, load_order_items_df, load_orders_df, load_products_df
from app.attribution.service import summarize_attribution
from app.core.errors import AppError
from app.db.session import get_db
from app.models.identity import Merchant
from app.models.opportunities import RevenueOpportunity
from app.security.auth import Principal, ensure_merchant_access, get_principal

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def _require_merchant(db: Session, merchant_id: uuid.UUID) -> Merchant:
    merchant = db.get(Merchant, merchant_id)
    if not merchant:
        raise AppError("MERCHANT_NOT_FOUND", "Merchant not found.", status_code=404)
    return merchant


@router.get("/summary")
def dashboard_summary(
    merchant_id: uuid.UUID,
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    """Every field here is computed live from the database — nothing is
    hard-coded. See app/analytics/metrics.py."""
    ensure_merchant_access(db, merchant_id, principal)
    _require_merchant(db, merchant_id)

    orders_df = load_orders_df(db, merchant_id)
    carts_df = load_carts_df(db, merchant_id)
    metrics = compute_revenue_metrics(orders_df, carts_df)

    opportunity_count = db.query(RevenueOpportunity).filter(
        RevenueOpportunity.merchant_id == merchant_id, RevenueOpportunity.status == "open"
    ).count()

    return {**metrics, **summarize_attribution(db, merchant_id), "open_opportunities": opportunity_count}


@router.get("/revenue-trend")
def revenue_trend(
    merchant_id: uuid.UUID, freq: str = "W",
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    ensure_merchant_access(db, merchant_id, principal)
    _require_merchant(db, merchant_id)
    orders_df = load_orders_df(db, merchant_id)
    return {"points": compute_revenue_trend(orders_df, freq=freq)}


@router.get("/top-products")
def top_products(
    merchant_id: uuid.UUID, limit: int = 10,
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    ensure_merchant_access(db, merchant_id, principal)
    _require_merchant(db, merchant_id)
    order_items_df = load_order_items_df(db, merchant_id)
    products_df = load_products_df(db, merchant_id)
    return {"products": compute_top_products(order_items_df, products_df, limit=limit)}

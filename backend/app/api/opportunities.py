import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.models.catalog import Product
from app.models.identity import Merchant
from app.models.opportunities import RevenueOpportunity
from app.opportunities.service import run_full_analytics
from app.security.auth import Principal, ensure_merchant_access, get_principal

router = APIRouter(prefix="/api/v1/opportunities", tags=["opportunities"])


def _serialize(opp: RevenueOpportunity, products_by_id: dict) -> dict:
    source = products_by_id.get(opp.source_product_id)
    target = products_by_id.get(opp.target_product_id)
    return {
        "id": str(opp.id),
        "type": opp.type,
        "source_product": {"id": str(source.id), "name": source.name} if source else None,
        "target_product": {"id": str(target.id), "name": target.name} if target else None,
        "reach_count": opp.reach_count,
        "confidence": float(opp.confidence),
        "historical_affinity": float(opp.historical_affinity),
        "estimated_conversion": float(opp.estimated_conversion),
        "estimated_revenue_amount": float(opp.estimated_revenue_amount),
        "risk_level": opp.risk_level,
        "priority_score": float(opp.priority_score),
        "evidence": opp.evidence_json,
        "status": opp.status,
        "created_at": opp.created_at.isoformat() if opp.created_at else None,
    }


@router.get("")
def list_opportunities(
    merchant_id: uuid.UUID,
    type: str | None = None,
    risk_level: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    ensure_merchant_access(db, merchant_id, principal)
    query = db.query(RevenueOpportunity).filter(
        RevenueOpportunity.merchant_id == merchant_id, RevenueOpportunity.status == "open"
    )
    if type:
        query = query.filter(RevenueOpportunity.type == type)
    if risk_level:
        query = query.filter(RevenueOpportunity.risk_level == risk_level)

    total = query.count()
    rows = query.order_by(RevenueOpportunity.priority_score.desc()).offset((page - 1) * page_size).limit(page_size).all()

    product_ids = {r.source_product_id for r in rows} | {r.target_product_id for r in rows}
    product_ids.discard(None)
    products_by_id = {p.id: p for p in db.query(Product).filter(Product.id.in_(product_ids))} if product_ids else {}

    return {
        "items": [_serialize(r, products_by_id) for r in rows],
        "page": page, "page_size": page_size, "total": total,
    }


@router.get("/{opportunity_id}")
def get_opportunity(
    opportunity_id: uuid.UUID,
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    opp = db.get(RevenueOpportunity, opportunity_id)
    if not opp:
        raise AppError("OPPORTUNITY_NOT_FOUND", "Opportunity not found.", status_code=404)
    ensure_merchant_access(db, opp.merchant_id, principal)
    product_ids = {opp.source_product_id, opp.target_product_id}
    product_ids.discard(None)
    products_by_id = {p.id: p for p in db.query(Product).filter(Product.id.in_(product_ids))} if product_ids else {}
    return _serialize(opp, products_by_id)


@router.post("/refresh")
def refresh_opportunities(
    merchant_id: uuid.UUID,
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    """Re-runs the full deterministic analytics pipeline (RFM, affinity,
    opportunity detection/scoring) for this merchant. Restricted to
    OWNER/ADMIN — matches the restriction used for approvals and settings,
    since this is a merchant-wide recompute, not a passive read."""
    ensure_merchant_access(db, merchant_id, principal, allowed_roles={"OWNER", "ADMIN"})
    merchant = db.get(Merchant, merchant_id)
    if not merchant:
        raise AppError("MERCHANT_NOT_FOUND", "Merchant not found.", status_code=404)
    summary = run_full_analytics(db, merchant_id)
    return {"opportunities_detected": summary["opportunities_detected"], "by_type": summary["opportunities_by_type"]}

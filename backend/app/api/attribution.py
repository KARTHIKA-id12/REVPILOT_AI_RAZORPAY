import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.attribution.service import summarize_attribution
from app.core.errors import AppError
from app.db.session import get_db
from app.models.campaigns import Campaign
from app.models.identity import Merchant
from app.models.ops import RevenueAttribution
from app.security.auth import Principal, ensure_merchant_access, get_principal

router = APIRouter(prefix="/api/v1/attribution", tags=["revenue-attribution"])


def _merchant_or_404(db: Session, merchant_id: uuid.UUID) -> None:
    if not db.get(Merchant, merchant_id):
        raise AppError("MERCHANT_NOT_FOUND", "Merchant not found.", status_code=404)


@router.get("/summary")
def attribution_summary(
    merchant_id: uuid.UUID,
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    ensure_merchant_access(db, merchant_id, principal)
    _merchant_or_404(db, merchant_id)
    return summarize_attribution(db, merchant_id)


@router.get("/campaigns")
def campaign_attribution(
    merchant_id: uuid.UUID,
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    ensure_merchant_access(db, merchant_id, principal)
    _merchant_or_404(db, merchant_id)
    campaigns = db.query(Campaign).filter(Campaign.merchant_id == merchant_id).order_by(Campaign.created_at.desc()).all()
    result = []
    for campaign in campaigns:
        rows = db.query(RevenueAttribution).filter(RevenueAttribution.campaign_id == campaign.id).all()
        revenue = round(sum(float(row.amount) for row in rows), 2)
        converted = len({row.customer_id for row in rows})
        # budget_amount is a cap, not a spend ledger. Return ROAS against
        # that cap explicitly rather than mislabeling it as causal ROI.
        result.append({
            "campaign_id": str(campaign.id),
            "name": campaign.name,
            "status": campaign.status,
            "attributed_revenue": revenue,
            "customers_converted": converted,
            "orders_attributed": len(rows),
            "average_order_value": round(revenue / len(rows), 2) if rows else 0,
            "roas_against_budget_cap": round(revenue / float(campaign.budget_amount), 2) if campaign.budget_amount else None,
            "incremental_revenue": None,
            "incrementality_note": "Not claimed without a controlled holdout or experiment.",
        })
    return {"items": result}
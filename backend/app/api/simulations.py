import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.campaigns.inputs import resolve_product_ids_and_confidence
from app.campaigns.simulation import compare_discount_scenarios
from app.core.errors import AppError
from app.db.session import get_db
from app.models.catalog import Product
from app.models.identity import Merchant
from app.security.auth import Principal, ensure_merchant_access, get_principal

router = APIRouter(prefix="/api/v1/simulations", tags=["simulations"])


class CompareRequest(BaseModel):
    opportunity_id: uuid.UUID | None = None
    product_ids: list[uuid.UUID] | None = None
    discount_percents: list[float] = Field(default_factory=lambda: [5, 10, 15])

    @field_validator("discount_percents")
    @classmethod
    def bounded_discounts(cls, v: list[float]) -> list[float]:
        if not v:
            raise ValueError("discount_percents cannot be empty")
        if len(v) > 8:
            raise ValueError("at most 8 scenarios can be compared at once")
        for pct in v:
            if pct < 0 or pct > 100:
                raise ValueError(f"discount_percent {pct} must be between 0 and 100")
        return v


@router.post("/compare")
def compare_scenarios(
    merchant_id: uuid.UUID, body: CompareRequest,
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    """Runs the same deterministic simulation math across multiple
    discount levels — this is the backend for 'what happens if I offer
    12% instead of 10%?'. Every input is recomputed from real transaction
    data (or a stored opportunity's evidence); nothing here is supplied
    by the caller except which product(s) and which discounts to compare."""
    ensure_merchant_access(db, merchant_id, principal)
    merchant = db.get(Merchant, merchant_id)
    if not merchant:
        raise AppError("MERCHANT_NOT_FOUND", "Merchant not found.", status_code=404)

    if not body.opportunity_id and not body.product_ids:
        raise AppError("MISSING_TARGET", "Provide either opportunity_id or product_ids.", status_code=422)

    resolved = resolve_product_ids_and_confidence(
        db, merchant_id, opportunity_id=body.opportunity_id, product_ids=body.product_ids,
    )
    if not resolved.get("found"):
        raise AppError("SIMULATION_TARGET_NOT_FOUND", "No matching opportunity or products found for this merchant.", status_code=404)

    products = {p.id: p for p in db.query(Product).filter(Product.id.in_(resolved["product_ids"]))}
    scenarios = compare_discount_scenarios(
        eligible_customers=resolved["eligible_customers"], average_order_value=resolved["average_order_value"],
        organic_confidence=resolved["organic_confidence"], discount_percents=body.discount_percents,
    )
    best = max((s for s in scenarios if s["roi"] is not None), key=lambda s: s["roi"], default=None)

    return {
        "products": [{"id": str(pid), "name": p.name} for pid, p in products.items()],
        "eligible_customers": resolved["eligible_customers"],
        "organic_confidence": resolved["organic_confidence"],
        "scenarios": scenarios,
        "recommended_discount_percent": best["discount_percent"] if best else None,
    }

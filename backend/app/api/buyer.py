import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.buyer.service import apply_cart_action, buyer_query, compare_products, get_or_create_cart, serialize_cart
from app.core.errors import AppError
from app.db.session import get_db
from app.models.identity import Merchant

router = APIRouter(prefix="/api/v1/agent", tags=["ai-buyer"])


def _require_merchant(db: Session, merchant_id: uuid.UUID) -> Merchant:
    merchant = db.get(Merchant, merchant_id)
    if not merchant:
        raise AppError("MERCHANT_NOT_FOUND", "Merchant not found.", status_code=404)
    return merchant


class BuyerQueryRequest(BaseModel):
    merchant_id: uuid.UUID
    query: str = Field(min_length=2, max_length=500)
    max_budget: float | None = Field(default=None, gt=0)

    @field_validator("query")
    @classmethod
    def meaningful_query(cls, value: str) -> str:
        return value.strip()


@router.post("/buyer/query")
def query_buyer(body: BuyerQueryRequest, db: Session = Depends(get_db)):
    _require_merchant(db, body.merchant_id)
    return buyer_query(db, body.merchant_id, body.query, body.max_budget)


@router.get("/compare")
def compare(
    merchant_id: uuid.UUID,
    product_ids: list[uuid.UUID] = Query(..., min_length=2, max_length=4),
    db: Session = Depends(get_db),
):
    _require_merchant(db, merchant_id)
    return compare_products(db, merchant_id, product_ids)


class CartActionRequest(BaseModel):
    merchant_id: uuid.UUID
    session_ref: str = Field(min_length=8, max_length=255)
    action: Literal["add", "set", "remove", "clear"]
    product_id: uuid.UUID | None = None
    quantity: int | None = Field(default=None, ge=1, le=100)
    customer_id: uuid.UUID | None = None
    max_total: float | None = Field(default=None, gt=0)

    @field_validator("session_ref")
    @classmethod
    def normalize_session(cls, value: str) -> str:
        return value.strip()


@router.get("/cart")
def get_cart(
    merchant_id: uuid.UUID,
    session_ref: str = Query(..., min_length=8, max_length=255),
    db: Session = Depends(get_db),
):
    _require_merchant(db, merchant_id)
    cart = get_or_create_cart(db, merchant_id, session_ref.strip())
    result = serialize_cart(db, cart)
    db.commit()
    return result


@router.post("/cart")
def mutate_cart(body: CartActionRequest, db: Session = Depends(get_db)):
    _require_merchant(db, body.merchant_id)
    result = apply_cart_action(
        db,
        body.merchant_id,
        session_ref=body.session_ref,
        action=body.action,
        product_id=body.product_id,
        quantity=body.quantity,
        customer_id=body.customer_id,
        max_total=body.max_total,
    )
    db.commit()
    return result
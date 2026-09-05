import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.checkout.service import confirm_checkout, preview_checkout, verify_checkout_payment
from app.core.errors import AppError
from app.db.session import get_db
from app.models.identity import Merchant

router = APIRouter(prefix="/api/v1/agent/checkout", tags=["ai-buyer-checkout"])


def _require_merchant(db: Session, merchant_id: uuid.UUID) -> None:
    if not db.get(Merchant, merchant_id):
        raise AppError("MERCHANT_NOT_FOUND", "Merchant not found.", status_code=404)


class CheckoutSessionRequest(BaseModel):
    merchant_id: uuid.UUID
    session_ref: str = Field(min_length=8, max_length=255)


@router.post("/preview")
def checkout_preview(body: CheckoutSessionRequest, db: Session = Depends(get_db)):
    _require_merchant(db, body.merchant_id)
    return preview_checkout(db, body.merchant_id, body.session_ref.strip())


class CheckoutConfirmRequest(CheckoutSessionRequest):
    preview_id: uuid.UUID
    confirmed: bool
    buyer_name: str = Field(min_length=2, max_length=255)
    buyer_email: str = Field(min_length=5, max_length=255)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=255)

    @field_validator("buyer_email")
    @classmethod
    def validate_email_shape(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("buyer_email must be a valid email address")
        return value


@router.post("/confirm")
def checkout_confirm(body: CheckoutConfirmRequest, db: Session = Depends(get_db)):
    _require_merchant(db, body.merchant_id)
    return confirm_checkout(
        db,
        body.merchant_id,
        session_ref=body.session_ref.strip(),
        preview_id=body.preview_id,
        confirmed=body.confirmed,
        buyer_name=body.buyer_name,
        buyer_email=body.buyer_email,
        idempotency_key=body.idempotency_key,
    )


class CheckoutVerifyRequest(BaseModel):
    merchant_id: uuid.UUID
    order_id: uuid.UUID
    provider_payment_id: str | None = Field(default=None, max_length=255)
    razorpay_signature: str | None = Field(default=None, max_length=255)
    demo: bool = False


@router.post("/verify")
def checkout_verify(body: CheckoutVerifyRequest, db: Session = Depends(get_db)):
    _require_merchant(db, body.merchant_id)
    return verify_checkout_payment(
        db,
        body.merchant_id,
        order_id=body.order_id,
        provider_payment_id=body.provider_payment_id,
        razorpay_signature=body.razorpay_signature,
        demo=body.demo,
    )
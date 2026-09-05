import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.catalog.agent_catalog import get_catalog, get_categories, get_product, recommend_products, search_catalog
from app.core.errors import AppError
from app.db.session import get_db
from app.models.identity import Merchant

router = APIRouter(prefix="/api/v1/agent", tags=["agent-catalog"])


def _require_merchant(db: Session, merchant_id: uuid.UUID) -> Merchant:
    merchant = db.get(Merchant, merchant_id)
    if not merchant:
        raise AppError("MERCHANT_NOT_FOUND", "Merchant not found.", status_code=404)
    return merchant


@router.get("/catalog")
def catalog(merchant_id: uuid.UUID, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    _require_merchant(db, merchant_id)
    return get_catalog(db, merchant_id, page, page_size)


@router.get("/catalog/search")
def catalog_search(
    merchant_id: uuid.UUID, q: str | None = None, min_price: float | None = None, max_price: float | None = None,
    category: str | None = None, in_stock_only: bool = False, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    _require_merchant(db, merchant_id)
    return search_catalog(
        db, merchant_id, query_text=q, min_price=min_price, max_price=max_price,
        category=category, in_stock_only=in_stock_only, page=page, page_size=page_size,
    )


@router.get("/products/{product_id}")
def product_detail(product_id: uuid.UUID, merchant_id: uuid.UUID, db: Session = Depends(get_db)):
    _require_merchant(db, merchant_id)
    product = get_product(db, merchant_id, product_id)
    if not product:
        # Deliberately explicit "not found" - never a best-guess
        # substitute. This is what prevents an AI buyer from being told
        # about a product that doesn't exist in this merchant's catalog.
        raise AppError("PRODUCT_NOT_FOUND", "No matching product in this merchant's catalog.", status_code=404)
    return product


@router.get("/categories")
def categories(merchant_id: uuid.UUID, db: Session = Depends(get_db)):
    _require_merchant(db, merchant_id)
    return {"items": get_categories(db, merchant_id)}


@router.get("/recommendations")
def recommendations(merchant_id: uuid.UUID, intent: str, max_price: float | None = None, limit: int = Query(5, ge=1, le=20), db: Session = Depends(get_db)):
    _require_merchant(db, merchant_id)
    if not intent or len(intent.strip()) < 2:
        raise AppError("INVALID_INTENT", "The 'intent' query parameter is required and must be meaningful text.", status_code=422)
    items = recommend_products(db, merchant_id, intent=intent, max_price=max_price, limit=limit)
    return {"items": items, "found": len(items) > 0}

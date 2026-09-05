import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.catalog import Product
from app.models.customers import Customer
from app.security.auth import Principal, ensure_merchant_access, get_principal

router = APIRouter(prefix="/api/v1/merchant", tags=["merchant-data"])


@router.get("/customers")
def list_customers(
    merchant_id: uuid.UUID,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    ensure_merchant_access(db, merchant_id, principal)
    query = db.query(Customer).filter(Customer.merchant_id == merchant_id)
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter((Customer.name.ilike(term)) | (Customer.email.ilike(term)))
    total = query.count()
    items = query.order_by(Customer.total_spend.desc(), Customer.name.asc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [
            {
                "id": str(item.id), "name": item.name, "email": item.email,
                "order_count": item.order_count, "total_spend": float(item.total_spend or 0),
                "last_order_at": item.last_order_at.isoformat() if item.last_order_at else None,
            }
            for item in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/products")
def list_products(
    merchant_id: uuid.UUID,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    ensure_merchant_access(db, merchant_id, principal)
    query = db.query(Product).filter(Product.merchant_id == merchant_id, Product.status == "active")
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter((Product.name.ilike(term)) | (Product.sku.ilike(term)))
    total = query.count()
    items = query.order_by(Product.name.asc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [
            {
                "id": str(item.id), "sku": item.sku, "name": item.name,
                "price_amount": float(item.price_amount), "currency": item.currency,
                "stock_qty": item.stock_qty, "stock_status": item.stock_status,
                "image_url": item.image_url,
            }
            for item in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
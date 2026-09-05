"""Agent-readable catalog. This is the machine-readable contract an AI
buyer (or any external agent) queries to discover products - see
docs/agent-commerce-api.md for the full contract documentation.

The single rule this entire module exists to enforce: an AI model must
never be able to invent a price, a stock count, or a product relationship.
Every field in every response here is read directly from the database at
request time. There is no LLM call anywhere in this file, and none of
these functions accept a price, quantity, or relationship as an input -
only search/filter criteria. If a search finds nothing, the response is
an honest empty list, never a plausible-sounding fabrication.
"""

import uuid

from sqlalchemy.orm import Session

from app.models.catalog import Product, ProductCategory, ProductRelation

RELATION_TYPE_KEYS = {
    "RELATED": "related_products",
    "FREQUENTLY_BOUGHT_WITH": "frequently_bought_with",
    "COMPATIBLE": "compatible_products",
}


def _category_name(db: Session, category_id: uuid.UUID | None) -> str | None:
    if not category_id:
        return None
    category = db.get(ProductCategory, category_id)
    return category.name if category else None


def _relations_for(db: Session, product_id: uuid.UUID) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {v: [] for v in RELATION_TYPE_KEYS.values()}
    rows = (
        db.query(ProductRelation, Product)
        .join(Product, Product.id == ProductRelation.related_product_id)
        .filter(ProductRelation.product_id == product_id)
        .all()
    )
    for relation, related_product in rows:
        key = RELATION_TYPE_KEYS.get(relation.relation_type)
        if key:
            result[key].append({"id": str(related_product.id), "name": related_product.name})
    return result


def serialize_product(db: Session, product: Product) -> dict:
    relations = _relations_for(db, product.id)
    is_purchasable = product.status == "active" and product.stock_status != "out_of_stock"
    return {
        "id": str(product.id),
        "sku": product.sku,
        "name": product.name,
        "description": product.description,
        "price": {"amount": float(product.price_amount), "currency": product.currency},
        "availability": {
            "in_stock": product.stock_status != "out_of_stock",
            "stock_status": product.stock_status,
            "quantity": product.stock_qty,
        },
        "category": _category_name(db, product.category_id),
        "specifications": product.specifications_json or {},
        "tags": product.tags_json or [],
        "use_cases": product.use_cases_json or [],
        "compatibility": product.compatibility_json or [],
        "related_products": relations["related_products"],
        "frequently_bought_with": relations["frequently_bought_with"],
        "compatible_products": relations["compatible_products"],
        "return_policy": product.return_policy,
        "shipping_info": product.shipping_info,
        "discount_eligible": product.discount_eligible,
        "purchase": {"available": is_purchasable},
    }


def get_catalog(db: Session, merchant_id: uuid.UUID, page: int, page_size: int) -> dict:
    query = db.query(Product).filter(Product.merchant_id == merchant_id, Product.status == "active")
    total = query.count()
    rows = query.order_by(Product.name).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [serialize_product(db, p) for p in rows], "page": page, "page_size": page_size, "total": total}


def search_catalog(
    db: Session, merchant_id: uuid.UUID, *, query_text: str | None, min_price: float | None, max_price: float | None,
    category: str | None, in_stock_only: bool, page: int, page_size: int,
) -> dict:
    q = db.query(Product).filter(Product.merchant_id == merchant_id, Product.status == "active")

    if query_text:
        pattern = f"%{query_text}%"
        q = q.filter(Product.name.ilike(pattern) | Product.description.ilike(pattern))
    if min_price is not None:
        q = q.filter(Product.price_amount >= min_price)
    if max_price is not None:
        q = q.filter(Product.price_amount <= max_price)
    if in_stock_only:
        q = q.filter(Product.stock_status != "out_of_stock")
    if category:
        q = q.join(ProductCategory, ProductCategory.id == Product.category_id).filter(ProductCategory.name.ilike(f"%{category}%"))

    total = q.count()
    rows = q.order_by(Product.price_amount).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [serialize_product(db, p) for p in rows], "page": page, "page_size": page_size, "total": total}


def get_product(db: Session, merchant_id: uuid.UUID, product_id: uuid.UUID) -> dict | None:
    product = db.query(Product).filter(Product.id == product_id, Product.merchant_id == merchant_id).one_or_none()
    if not product:
        return None
    return serialize_product(db, product)


def get_categories(db: Session, merchant_id: uuid.UUID) -> list[dict]:
    categories = db.query(ProductCategory).filter(ProductCategory.merchant_id == merchant_id).all()
    result = []
    for category in categories:
        count = db.query(Product).filter(Product.category_id == category.id, Product.status == "active").count()
        result.append({"id": str(category.id), "name": category.name, "product_count": count})
    return result


def recommend_products(db: Session, merchant_id: uuid.UUID, *, intent: str, max_price: float | None, limit: int = 5) -> list[dict]:
    """Deterministic keyword matching against real use_cases/tags -
    NOT an LLM call. Ranks by number of matched terms, cheapest first as
    a tiebreak. If nothing matches, returns an empty list rather than a
    best-effort guess."""
    intent_terms = {t.strip().lower() for t in intent.replace(",", " ").split() if len(t.strip()) > 2}
    if not intent_terms:
        return []

    query = db.query(Product).filter(Product.merchant_id == merchant_id, Product.status == "active", Product.stock_status != "out_of_stock")
    if max_price is not None:
        query = query.filter(Product.price_amount <= max_price)

    scored = []
    for product in query.all():
        haystack = {t.lower() for t in (product.use_cases_json or [])} | {t.lower() for t in (product.tags_json or [])}
        haystack.add(product.name.lower())
        match_count = sum(1 for term in intent_terms if any(term in item for item in haystack))
        if match_count > 0:
            scored.append((match_count, float(product.price_amount), product))

    scored.sort(key=lambda t: (-t[0], t[1]))
    return [serialize_product(db, p) for _, _, p in scored[:limit]]

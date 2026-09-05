"""Services for the AI Buyer experience.

The buyer may express intent in natural language, and — when a free
open-model provider is configured (see app.agents.providers) — that
free-text understanding is real (Hugging Face Inference Providers, see
app/agents/huggingface_provider.py). But the catalog, prices, stock,
relationships, cart state, and totals ALWAYS come from the database, and
ranking itself is deterministic term-matching (see _rank_products). The
LLM, when used, only proposes a bounded budget and a short list of
search keywords to widen what's matched against the real catalog — it
never invents a product, a price, or availability. With no provider
configured (demo mode default), a deterministic keyword/regex extractor
does the same job with zero external dependency; see
_resolve_buyer_intent() for exactly where the two paths meet, and
docs/system-overview.md Section 1 for the fuller explanation.
"""

from __future__ import annotations

import json
import re
import uuid
from collections import defaultdict
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.catalog.agent_catalog import serialize_product
from app.core.errors import AppError
from app.models.catalog import Product, ProductCategory, ProductRelation
from app.models.commerce import Cart, CartItem, Order, OrderItem

if TYPE_CHECKING:
    from app.buyer.intent_schema import BuyerIntent


def _money(value: Decimal | float | int | None) -> float:
    return round(float(value or 0), 2)


def _merchant_product(db: Session, merchant_id: uuid.UUID, product_id: uuid.UUID) -> Product:
    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.merchant_id == merchant_id, Product.status == "active")
        .one_or_none()
    )
    if not product:
        raise AppError("PRODUCT_NOT_FOUND", "No active product with that ID exists in this merchant's catalog.", status_code=404)
    return product


def _ensure_customer_belongs_to_merchant(db: Session, merchant_id: uuid.UUID, customer_id: uuid.UUID | None) -> None:
    if customer_id is None:
        return
    from app.models.customers import Customer

    if not db.query(Customer).filter(Customer.id == customer_id, Customer.merchant_id == merchant_id).one_or_none():
        raise AppError("CUSTOMER_NOT_FOUND", "The customer does not belong to this merchant.", status_code=404)


def _active_cart(db: Session, merchant_id: uuid.UUID, session_ref: str) -> Cart | None:
    return (
        db.query(Cart)
        .filter(Cart.merchant_id == merchant_id, Cart.session_ref == session_ref, Cart.status == "active")
        .order_by(Cart.created_at.desc())
        .first()
    )


def get_or_create_cart(
    db: Session, merchant_id: uuid.UUID, session_ref: str, customer_id: uuid.UUID | None = None
) -> Cart:
    _ensure_customer_belongs_to_merchant(db, merchant_id, customer_id)
    cart = _active_cart(db, merchant_id, session_ref)
    if cart:
        if customer_id and cart.customer_id and cart.customer_id != customer_id:
            raise AppError("CART_SESSION_MISMATCH", "This cart session belongs to a different customer.", status_code=409)
        if customer_id and not cart.customer_id:
            cart.customer_id = customer_id
        return cart

    cart = Cart(merchant_id=merchant_id, customer_id=customer_id, session_ref=session_ref, status="active")
    db.add(cart)
    db.flush()
    return cart


def serialize_cart(db: Session, cart: Cart) -> dict:
    rows = (
        db.query(CartItem, Product)
        .join(Product, Product.id == CartItem.product_id)
        .filter(CartItem.cart_id == cart.id)
        .order_by(CartItem.id)
        .all()
    )
    items = []
    subtotal = 0.0
    issues: list[dict] = []
    for item, product in rows:
        unit_price = _money(product.price_amount)
        line_total = round(unit_price * item.quantity, 2)
        subtotal += line_total
        available = product.status == "active" and product.stock_status != "out_of_stock" and product.stock_qty >= item.quantity
        if not available:
            issues.append(
                {
                    "product_id": str(product.id),
                    "product_name": product.name,
                    "reason": "Product is unavailable at the requested quantity.",
                }
            )
        items.append(
            {
                "id": str(item.id),
                "product_id": str(product.id),
                "name": product.name,
                "sku": product.sku,
                "quantity": item.quantity,
                "unit_price": {"amount": unit_price, "currency": product.currency},
                "line_total": {"amount": line_total, "currency": product.currency},
                "availability": {
                    "in_stock": product.stock_status != "out_of_stock",
                    "quantity": product.stock_qty,
                    "available_for_cart": available,
                },
                "image_url": product.image_url,
            }
        )

    return {
        "id": str(cart.id),
        "session_ref": cart.session_ref,
        "customer_id": str(cart.customer_id) if cart.customer_id else None,
        "status": cart.status,
        "items": items,
        "subtotal": {"amount": round(subtotal, 2), "currency": "INR"},
        "shipping": {"amount": 0.0, "currency": "INR"},
        "total": {"amount": round(subtotal, 2), "currency": "INR"},
        "item_count": sum(i["quantity"] for i in items),
        "can_checkout": bool(items) and not issues,
        "issues": issues,
    }


def apply_cart_action(
    db: Session,
    merchant_id: uuid.UUID,
    *,
    session_ref: str,
    action: str,
    product_id: uuid.UUID | None,
    quantity: int | None,
    customer_id: uuid.UUID | None,
    max_total: float | None,
) -> dict:
    cart = get_or_create_cart(db, merchant_id, session_ref, customer_id)
    current = {
        item.product_id: item
        for item in db.query(CartItem).filter(CartItem.cart_id == cart.id).all()
    }

    if action in {"add", "set", "remove"}:
        if product_id is None:
            raise AppError("PRODUCT_REQUIRED", f"product_id is required for the '{action}' cart action.", status_code=422)
        product = _merchant_product(db, merchant_id, product_id)
        existing = current.get(product_id)

        if action in {"add", "set"}:
            if product.stock_status == "out_of_stock" or product.stock_qty < 1:
                raise AppError("OUT_OF_STOCK", f"{product.name} is currently out of stock.", status_code=409)
            requested = quantity or 1
            target_quantity = requested if action == "set" else (existing.quantity if existing else 0) + requested
            if target_quantity > product.stock_qty:
                raise AppError(
                    "INSUFFICIENT_STOCK",
                    f"Only {product.stock_qty} unit(s) of {product.name} are available.",
                    status_code=409,
                    details={"available_quantity": product.stock_qty},
                )
            if max_total is not None:
                projected = sum(
                    _money(p.price_amount) * (i.quantity if pid != product_id else target_quantity)
                    for pid, i in current.items()
                    for p in [db.get(Product, pid)]
                )
                if not existing:
                    projected += _money(product.price_amount) * target_quantity
                if projected > max_total:
                    raise AppError(
                        "BUDGET_EXCEEDED",
                        f"That would take the cart to ₹{projected:,.0f}, above your ₹{max_total:,.0f} budget.",
                        status_code=422,
                        details={"cart_total": round(projected, 2), "max_total": max_total},
                    )
            if existing:
                existing.quantity = target_quantity
                existing.unit_price_amount = product.price_amount
            else:
                db.add(CartItem(cart_id=cart.id, product_id=product.id, quantity=target_quantity, unit_price_amount=product.price_amount))
        elif existing:
            remove_quantity = quantity or existing.quantity
            if remove_quantity >= existing.quantity:
                db.delete(existing)
            else:
                existing.quantity -= remove_quantity
        else:
            raise AppError("CART_ITEM_NOT_FOUND", "That product is not in the cart.", status_code=404)
    elif action == "clear":
        for item in current.values():
            db.delete(item)
    else:
        raise AppError("INVALID_CART_ACTION", "Use add, set, remove, or clear.", status_code=422)

    db.flush()
    return serialize_cart(db, cart)


_BUYER_INTENT_SYSTEM_PROMPT = (
    "You extract shopping intent for a gaming/desk-accessories online store. Given the "
    "buyer's message, respond with ONLY a single JSON object (no prose, no markdown "
    'fences) with exactly these keys:\n'
    '  "max_budget": a number (the buyer\'s stated budget in rupees), or null if none was stated\n'
    '  "search_terms": a JSON array of up to 8 short lowercase keywords capturing the '
    "product types or use cases mentioned (e.g. [\"gaming\", \"keyboard\", \"wireless\"])\n"
    "Never invent a specific product name, price, or availability — you are only "
    "extracting what the buyer said, not answering it."
)


def _extract_intent_with_llm(query: str) -> BuyerIntent | None:
    """Returns a validated BuyerIntent from a real LLM call, or None on
    ANY failure — network error, timeout, malformed JSON, or an
    out-of-range value the schema rejects. None means "fall back to the
    deterministic extractor"; this function must never raise."""
    from app.agents.providers import get_ai_provider
    from app.buyer.intent_schema import BuyerIntent

    try:
        provider = get_ai_provider()
        raw = provider.complete(
            system=_BUYER_INTENT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": query}],
            response_schema={"type": "object"},
        )
        return BuyerIntent.model_validate(json.loads(raw))
    except Exception:  # noqa: BLE001 -- any provider/parse failure must gracefully fall back, never break the buyer's chat
        return None


def _resolve_buyer_intent(query: str, max_budget: float | None) -> tuple[float | None, set[str], str]:
    """Single seam between the free open-model path and the deterministic
    fallback. Returns (budget, terms, source) — source is surfaced in the
    API response ("llm" or "keyword") for transparency about which path
    actually ran, per merchant-facing audit expectations."""
    from app.core.config import get_settings

    settings = get_settings()
    keyword_terms = _intent_terms(query)

    if settings.AI_PROVIDER != "mock" and settings.AI_API_KEY:
        llm_intent = _extract_intent_with_llm(query)
        if llm_intent is not None:
            # Union, not replace: the LLM's keywords widen matching, but
            # never lose whatever the deterministic extractor already
            # found directly in the buyer's own words.
            terms = keyword_terms | {t.lower() for t in llm_intent.search_terms}
            budget = max_budget if max_budget is not None else (llm_intent.max_budget if llm_intent.max_budget is not None else _extract_budget(query))
            return budget, terms, "llm"

    budget = max_budget if max_budget is not None else _extract_budget(query)
    return budget, keyword_terms, "keyword"


def _extract_budget(query: str) -> float | None:
    cleaned = query.lower().replace(",", "")
    patterns = [
        r"(?:₹|rs\.?|inr)\s*(\d+(?:\.\d+)?)",
        r"(?:under|below|within|budget(?:\s+of)?|less\s+than)\s*(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if match:
            return float(match.group(1))
    return None


def _intent_terms(query: str) -> set[str]:
    stop_words = {
        "under", "below", "within", "budget", "with", "for", "and", "the", "less",
        "than", "need", "want", "show", "find", "something", "please",
    }
    return {
        word
        for word in re.findall(r"[a-z0-9]+", query.lower())
        if len(word) > 2 and word not in stop_words and not word.isdigit()
    }


def _rank_products(db: Session, merchant_id: uuid.UUID, query: str, max_budget: float | None, terms: set[str] | None = None) -> list[tuple[float, Product]]:
    terms = terms if terms is not None else _intent_terms(query)
    products_query = db.query(Product).filter(
        Product.merchant_id == merchant_id,
        Product.status == "active",
        Product.stock_status != "out_of_stock",
    )
    products = products_query.all()
    product_ids = [p.id for p in products]
    popularity = defaultdict(int)
    if product_ids:
        popularity_rows = (
            db.query(OrderItem.product_id, func.sum(OrderItem.quantity))
            .join(Order, Order.id == OrderItem.order_id)
            .filter(Order.merchant_id == merchant_id, Order.status == "paid", OrderItem.product_id.in_(product_ids))
            .group_by(OrderItem.product_id)
            .all()
        )
        popularity.update({product_id: int(units or 0) for product_id, units in popularity_rows})

    category_names = {
        category.id: category.name.lower()
        for category in db.query(ProductCategory).filter(ProductCategory.merchant_id == merchant_id).all()
    }
    ranked: list[tuple[float, Product]] = []
    for product in products:
        price = _money(product.price_amount)
        if max_budget is not None and price > max_budget:
            continue
        haystack = " ".join(
            [product.name, product.description or "", category_names.get(product.category_id, "")]
            + (product.tags_json or [])
            + (product.use_cases_json or [])
        ).lower()
        matches = sum(1 for term in terms if term in haystack)
        if matches == 0 and terms:
            continue
        # Relevance is primary; popularity and lower price are deterministic
        # tie breakers, not invented recommendation confidence.
        score = matches * 100 + min(popularity[product.id], 100) * 0.01
        ranked.append((score, product))
    ranked.sort(key=lambda pair: (-pair[0], _money(pair[1].price_amount), pair[1].name))
    return ranked


def buyer_query(db: Session, merchant_id: uuid.UUID, query: str, max_budget: float | None = None) -> dict:
    budget, terms, intent_source = _resolve_buyer_intent(query, max_budget)
    ranked = _rank_products(db, merchant_id, query, budget, terms=terms)
    products = [serialize_product(db, product) for _, product in ranked[:8]]

    bundles = []
    setup_words = {"setup", "bundle", "combo", "kit", "desk"}
    if terms & setup_words or len(ranked) >= 2:
        ranked_by_id = {product.id: (score, product) for score, product in ranked}
        relation_rows = (
            db.query(ProductRelation)
            .filter(ProductRelation.product_id.in_(list(ranked_by_id)), ProductRelation.relation_type.in_(("FREQUENTLY_BOUGHT_WITH", "COMPATIBLE")))
            .all()
        )
        seen: set[frozenset[uuid.UUID]] = set()
        for relation in relation_rows:
            if relation.related_product_id not in ranked_by_id:
                continue
            first = ranked_by_id[relation.product_id][1]
            second = ranked_by_id[relation.related_product_id][1]
            pair = frozenset((first.id, second.id))
            if pair in seen:
                continue
            seen.add(pair)
            total = _money(first.price_amount) + _money(second.price_amount)
            if budget is not None and total > budget:
                continue
            relation_label = "frequently bought together" if relation.relation_type == "FREQUENTLY_BOUGHT_WITH" else "compatible"
            bundles.append(
                {
                    "id": f"{first.id}-{second.id}",
                    "name": f"{first.name} + {second.name}",
                    "product_ids": [str(first.id), str(second.id)],
                    "products": [serialize_product(db, first), serialize_product(db, second)],
                    "total": {"amount": total, "currency": first.currency},
                    "reason": f"These products are {relation_label} in the merchant catalog and both are currently in stock.",
                }
            )
        bundles.sort(key=lambda bundle: bundle["total"]["amount"])

    if bundles:
        explanation = bundles[0]["reason"]
    elif products:
        explanation = "These products match the use case and are currently available at live catalog prices."
    else:
        explanation = "No in-stock products matched that request. Try a different use case or a larger budget."

    return {
        "query": query,
        "intent": {
            "terms": sorted(terms),
            "max_budget": budget,
            "budget_source": "request" if max_budget is not None else (intent_source if budget is not None else None),
        },
        "intent_source": intent_source,
        "products": products,
        "bundles": bundles[:3],
        "found": bool(products or bundles),
        "explanation": explanation,
    }


def compare_products(db: Session, merchant_id: uuid.UUID, product_ids: list[uuid.UUID]) -> dict:
    if len(product_ids) < 2 or len(product_ids) > 4:
        raise AppError("INVALID_COMPARISON", "Compare between 2 and 4 products.", status_code=422)
    if len(set(product_ids)) != len(product_ids):
        raise AppError("INVALID_COMPARISON", "A comparison cannot contain the same product twice.", status_code=422)
    products = (
        db.query(Product)
        .filter(Product.merchant_id == merchant_id, Product.id.in_(product_ids), Product.status == "active")
        .all()
    )
    if len(products) != len(set(product_ids)):
        raise AppError("PRODUCT_NOT_FOUND", "Every compared product must be an active product in this merchant's catalog.", status_code=404)
    products.sort(key=lambda product: product_ids.index(product.id))
    serialized = [serialize_product(db, product) for product in products]
    return {
        "products": serialized,
        "comparison": {
            "lowest_price_product_id": str(min(products, key=lambda product: product.price_amount).id),
            "in_stock_product_ids": [str(product.id) for product in products if product.stock_status != "out_of_stock"],
            "shared_use_cases": sorted(set.intersection(*(set(product.use_cases_json or []) for product in products))),
        },
    }
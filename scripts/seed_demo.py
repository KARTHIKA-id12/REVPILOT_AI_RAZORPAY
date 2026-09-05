#!/usr/bin/env python3
"""Seed the RevPilot demo merchant: TechNest.

Generates a merchant, catalog, ~1,050 customers with distinct behavioral
profiles, and 2,000-5,000 orders/payments/carts shaped by those profiles
(recency, frequency, basket size, affinity, seasonality, failure rate) —
not uniform random noise. This is what gives Phase 4's RFM/affinity/
opportunity engines real signal to find.

Usage:
    python scripts/seed_demo.py            # seed (idempotent: wipes TechNest first)
    python scripts/seed_demo.py --reset    # same thing, explicit
"""

import random
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import delete  # noqa: E402

from app.db.seed_data.technest_catalog import PRODUCT_RELATIONS, PRODUCTS  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.campaigns import AgentPermission, PolicyRule  # noqa: E402
from app.models.catalog import Product, ProductCategory, ProductRelation  # noqa: E402
from app.models.commerce import Cart, CartItem, Order, OrderItem, Payment  # noqa: E402
from app.models.customers import Customer  # noqa: E402
from app.models.identity import Merchant, MerchantSettings, Permission, Role, User, UserMerchantRole  # noqa: E402
from app.models.opportunities import RevenueOpportunity  # noqa: E402
from app.security.passwords import hash_password  # noqa: E402
from app.services.merchant_cleanup import reset_merchant  # noqa: E402

RNG_SEED = 42
random.seed(RNG_SEED)

NOW = datetime.now(timezone.utc)
LOOKBACK_DAYS = 365

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Krishna", "Ishaan", "Rohan",
    "Ananya", "Diya", "Saanvi", "Aadhya", "Myra", "Anika", "Priya", "Kavya", "Riya", "Ishita",
    "Rahul", "Karan", "Nikhil", "Varun", "Siddharth", "Neha", "Pooja", "Sneha", "Divya", "Meera",
]
LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Iyer", "Nair", "Reddy", "Rao", "Menon", "Patel", "Shah",
    "Kapoor", "Malhotra", "Chopra", "Bose", "Mukherjee", "Pillai", "Krishnan", "Joshi", "Kulkarni", "Desai",
]


@dataclass
class CustomerProfile:
    code: str
    weight: float
    order_count_range: tuple[int, int]
    recency_days_range: tuple[int, int]  # how many days ago the *last* order landed
    basket_size_range: tuple[int, int]
    discount_probability: float
    order_value_multiplier: float = 1.0


# Deliberately distinct behavioral archetypes — these are inputs to
# generation, not outputs. Phase 4's RFM engine re-derives segments from
# the resulting orders; nothing here is written to customer_segments.
PROFILES = [
    CustomerProfile("champion", 0.08, (8, 15), (0, 20), (2, 4), 0.15, 1.15),
    CustomerProfile("loyal", 0.15, (5, 8), (0, 45), (1, 3), 0.18, 1.0),
    CustomerProfile("potential_loyalist", 0.15, (2, 4), (0, 40), (1, 2), 0.15, 0.95),
    CustomerProfile("new", 0.12, (1, 1), (0, 30), (1, 2), 0.10, 0.9),
    CustomerProfile("at_risk", 0.12, (3, 6), (90, 160), (1, 3), 0.20, 1.0),
    CustomerProfile("dormant", 0.15, (1, 3), (200, 360), (1, 2), 0.12, 0.85),
    CustomerProfile("high_value", 0.08, (2, 5), (0, 90), (2, 4), 0.10, 1.8),
    CustomerProfile("price_sensitive", 0.15, (4, 9), (0, 60), (1, 2), 0.45, 0.7),
]


def seasonality_weight(day_offset_from_today: int) -> float:
    """day_offset_from_today: 0 = today, 365 = a year ago. Returns a
    relative sampling weight so festive/year-end periods get more orders."""
    date = NOW - timedelta(days=day_offset_from_today)
    month, day = date.month, date.day
    if month == 11 or (month == 10 and day >= 15):
        return 1.9  # festive season
    if month == 12 or (month == 1 and day <= 5):
        return 1.4  # year-end
    if month in (6, 7):
        return 0.82  # monsoon lull
    return 1.0


def sample_order_date(recency_days_min: int, recency_days_max: int, is_last_order: bool) -> datetime:
    if is_last_order:
        offset = random.randint(recency_days_min, recency_days_max)
    else:
        # earlier orders scattered further back, still within lookback window
        offset = random.randint(recency_days_min, LOOKBACK_DAYS)
    # seasonality-weighted jitter: occasionally pull the date toward a
    # nearby high-weight day
    if random.random() < 0.3:
        candidates = [offset]
        for delta in (-10, -5, 5, 10):
            candidate = max(0, min(LOOKBACK_DAYS, offset + delta))
            candidates.append(candidate)
        weights = [seasonality_weight(c) for c in candidates]
        offset = random.choices(candidates, weights=weights, k=1)[0]
    return NOW - timedelta(days=offset, hours=random.randint(0, 23), minutes=random.randint(0, 59))


def build_affinity_map(product_ids: dict[str, uuid.UUID]) -> dict[uuid.UUID, list[tuple[uuid.UUID, float]]]:
    affinity: dict[uuid.UUID, list[tuple[uuid.UUID, float]]] = {}
    for key_a, key_b, _rel_type, weight in PRODUCT_RELATIONS:
        id_a, id_b = product_ids[key_a], product_ids[key_b]
        affinity.setdefault(id_a, []).append((id_b, weight))
        affinity.setdefault(id_b, []).append((id_a, weight))
    return affinity


def build_basket(
    products: list[Product],
    affinity_map: dict[uuid.UUID, list[tuple[uuid.UUID, float]]],
    basket_size_range: tuple[int, int],
) -> list[Product]:
    by_id = {p.id: p for p in products}
    seed = random.choices(products, weights=[float(p.price_amount) ** -0.3 for p in products], k=1)[0]
    basket = [seed]
    target_size = random.randint(*basket_size_range)

    while len(basket) < target_size:
        companions = affinity_map.get(basket[-1].id, [])
        added = False
        if companions and random.random() < 0.7:
            for companion_id, weight in sorted(companions, key=lambda x: -x[1]):
                if companion_id in by_id and by_id[companion_id] not in basket and random.random() < weight:
                    basket.append(by_id[companion_id])
                    added = True
                    break
        if not added:
            candidate = random.choice(products)
            if candidate not in basket:
                basket.append(candidate)
            else:
                break
    return basket


def main(reset: bool = True) -> None:
    db = SessionLocal()
    try:
        existing = db.query(Merchant).filter(Merchant.name == "TechNest").one_or_none()
        if existing and reset:
            print(f"Resetting existing TechNest merchant ({existing.id})...")
            reset_merchant(db, existing.id)

        print("Creating TechNest merchant...")
        merchant = Merchant(
            name="TechNest",
            category="Consumer Electronics / Gaming Accessories",
            description="A gaming and productivity accessories retailer selling keyboards, mice, "
            "headsets, monitors, and desk setup gear.",
            status="active",
        )
        db.add(merchant)
        db.flush()

        db.add(MerchantSettings(merchant_id=merchant.id, currency="INR", demo_mode=True, payment_provider="mock"))

        # Roles (global catalog, created once)
        role_names = ["OWNER", "ADMIN", "ANALYST", "VIEWER"]
        roles = {}
        for name in role_names:
            role = db.query(Role).filter(Role.name == name).one_or_none()
            if not role:
                role = Role(name=name)
                db.add(role)
                db.flush()
            roles[name] = role

        # Permission catalog (reference list, from docs/agent-tools-permissions-policy.md)
        permission_codes = [
            "VIEW_ANALYTICS", "VIEW_CUSTOMERS", "VIEW_PRODUCTS", "CREATE_CAMPAIGN_DRAFT",
            "SIMULATE_CAMPAIGN", "CREATE_DISCOUNT", "CREATE_PAYMENT_LINK", "CREATE_ORDER",
            "EXECUTE_FINANCIAL_ACTION", "CANCEL_PAYMENT_LINK", "REFUND_PAYMENT", "MODIFY_PRODUCT_PRICE",
        ]
        for code in permission_codes:
            if not db.query(Permission).filter(Permission.code == code).one_or_none():
                db.add(Permission(code=code, description=f"Agent permission: {code}"))

        demo_user = db.query(User).filter(User.email == "owner@technest.demo").one_or_none()
        if not demo_user:
            demo_user = User(email="owner@technest.demo", password_hash=hash_password("RevPilotDemo123!"), name="Asha Rao")
            db.add(demo_user)
            db.flush()
        db.add(UserMerchantRole(user_id=demo_user.id, merchant_id=merchant.id, role_id=roles["OWNER"].id))

        # Policy defaults (docs/agent-tools-permissions-policy.md §4)
        policy_defaults = {
            "MAX_DISCOUNT_PERCENT": 15,
            "MAX_CAMPAIGN_BUDGET": 5000,
            "MAX_DAILY_CAMPAIGNS": 50,
            "MAX_SINGLE_TRANSACTION": 10000,
            "REQUIRE_APPROVAL_FOR_FINANCIAL_ACTIONS": True,
            "NO_OUT_OF_STOCK_PRODUCTS": True,
            "NO_NEGATIVE_MARGIN_ACTIONS": True,
        }
        for code, value in policy_defaults.items():
            db.add(PolicyRule(merchant_id=merchant.id, code=code, value_json={"value": value}))

        # Permission defaults (§3)
        permission_defaults = {
            "VIEW_ANALYTICS": "ALLOW", "VIEW_CUSTOMERS": "ALLOW", "VIEW_PRODUCTS": "ALLOW",
            "CREATE_CAMPAIGN_DRAFT": "ALLOW", "SIMULATE_CAMPAIGN": "ALLOW",
            "CREATE_DISCOUNT": "APPROVAL", "CREATE_PAYMENT_LINK": "APPROVAL", "CREATE_ORDER": "APPROVAL",
            "EXECUTE_FINANCIAL_ACTION": "APPROVAL", "CANCEL_PAYMENT_LINK": "APPROVAL",
            "REFUND_PAYMENT": "DENY", "MODIFY_PRODUCT_PRICE": "DENY",
        }
        for code, mode in permission_defaults.items():
            db.add(AgentPermission(merchant_id=merchant.id, action_code=code, mode=mode))

        print("Creating catalog (12 products)...")
        categories: dict[str, ProductCategory] = {}
        for p in PRODUCTS:
            if p["category"] not in categories:
                cat = ProductCategory(merchant_id=merchant.id, name=p["category"])
                db.add(cat)
                db.flush()
                categories[p["category"]] = cat

        product_objs: dict[str, Product] = {}
        for p in PRODUCTS:
            product = Product(
                merchant_id=merchant.id,
                sku=p["sku"],
                name=p["name"],
                description=p["description"],
                price_amount=p["price_amount"],
                currency="INR",
                category_id=categories[p["category"]].id,
                stock_qty=p["stock_qty"],
                stock_status="in_stock",
                specifications_json=p["specifications"],
                tags_json=p["tags"],
                use_cases_json=p["use_cases"],
                compatibility_json=p["compatibility"],
                return_policy="7-day free returns on unused items in original packaging.",
                shipping_info="Ships in 2-4 business days. Free shipping over ₹1,500.",
                discount_eligible=True,
                status="active",
            )
            db.add(product)
            product_objs[p["key"]] = product
        db.flush()

        for key_a, key_b, rel_type, _weight in PRODUCT_RELATIONS:
            db.add(ProductRelation(product_id=product_objs[key_a].id, related_product_id=product_objs[key_b].id, relation_type=rel_type))
            db.add(ProductRelation(product_id=product_objs[key_b].id, related_product_id=product_objs[key_a].id, relation_type=rel_type))

        db.commit()

        products = list(product_objs.values())
        product_ids = {k: v.id for k, v in product_objs.items()}
        affinity_map = build_affinity_map(product_ids)

        print("Generating ~180 customers with distinct behavioral profiles...")
        n_customers = 180
        profile_weights = [p.weight for p in PROFILES]
        customers: list[Customer] = []
        customer_profiles: list[CustomerProfile] = []
        used_emails: set[str] = set()

        for i in range(n_customers):
            profile = random.choices(PROFILES, weights=profile_weights, k=1)[0]
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            email = f"{first.lower()}.{last.lower()}{i}@example.com"
            while email in used_emails:
                email = f"{first.lower()}.{last.lower()}{i}.{random.randint(1,999)}@example.com"
            used_emails.add(email)

            customer = Customer(
                merchant_id=merchant.id,
                name=f"{first} {last}",
                email=email,
                phone=f"+91{random.randint(7000000000, 9999999999)}",
                total_spend=0,
                order_count=0,
            )
            customers.append(customer)
            customer_profiles.append(profile)

        db.add_all(customers)
        db.flush()

        print("Generating orders, order items, and payments...")
        total_orders = 0
        total_paid_revenue = 0.0
        total_abandoned_carts = 0

        for customer, profile in zip(customers, customer_profiles, strict=True):
            n_orders = random.randint(*profile.order_count_range)
            customer_last_order_at = None
            customer_first_order_at = None
            paid_total = 0.0
            paid_count = 0

            for order_idx in range(n_orders):
                is_last = order_idx == n_orders - 1
                order_date = sample_order_date(profile.recency_days_range[0], profile.recency_days_range[1], is_last)

                basket = build_basket(products, affinity_map, profile.basket_size_range)
                subtotal = 0.0
                items_payload = []
                for product in basket:
                    qty = 1 if random.random() > 0.15 else 2
                    line_total = float(product.price_amount) * qty
                    subtotal += line_total
                    items_payload.append((product, qty))

                subtotal *= profile.order_value_multiplier
                discount = 0.0
                if random.random() < profile.discount_probability:
                    discount = round(subtotal * random.uniform(0.05, 0.15), 2)
                shipping = 0.0 if subtotal >= 1500 else 99.0
                total = round(subtotal - discount + shipping, 2)

                status_roll = random.random()
                if status_roll < 0.92:
                    order_status, payment_status = "paid", "paid"
                elif status_roll < 0.97:
                    order_status, payment_status = "failed", "failed"
                else:
                    order_status, payment_status = "cancelled", "failed"

                order = Order(
                    merchant_id=merchant.id,
                    customer_id=customer.id,
                    status=order_status,
                    subtotal_amount=round(subtotal, 2),
                    discount_amount=discount,
                    shipping_amount=shipping,
                    total_amount=total,
                    currency="INR",
                    source="direct",
                    created_at=order_date,
                    updated_at=order_date,
                )
                db.add(order)
                db.flush()

                for product, qty in items_payload:
                    db.add(OrderItem(order_id=order.id, product_id=product.id, quantity=qty, unit_price_amount=product.price_amount))

                payment = Payment(
                    merchant_id=merchant.id,
                    order_id=order.id,
                    provider="mock",
                    provider_payment_id=f"mock_pay_{uuid.uuid4().hex[:16]}",
                    amount=total,
                    currency="INR",
                    status=payment_status,
                    idempotency_key=f"seed_{order.id}",
                    created_at=order_date,
                    updated_at=order_date,
                )
                db.add(payment)

                total_orders += 1
                if order_status == "paid":
                    paid_total += total
                    paid_count += 1
                    total_paid_revenue += total
                    if customer_first_order_at is None or order_date < customer_first_order_at:
                        customer_first_order_at = order_date
                    if customer_last_order_at is None or order_date > customer_last_order_at:
                        customer_last_order_at = order_date

            customer.total_spend = round(paid_total, 2)
            customer.order_count = paid_count
            customer.first_order_at = customer_first_order_at
            customer.last_order_at = customer_last_order_at

            # Abandoned cart: ~15% chance of an extra session that never converted
            if random.random() < 0.15:
                cart_date = sample_order_date(0, LOOKBACK_DAYS, True)
                cart = Cart(
                    merchant_id=merchant.id,
                    customer_id=customer.id,
                    session_ref=f"sess_{uuid.uuid4().hex[:12]}",
                    status="abandoned",
                    created_at=cart_date,
                    updated_at=cart_date,
                )
                db.add(cart)
                db.flush()
                basket = build_basket(products, affinity_map, (1, 2))
                for product in basket:
                    db.add(CartItem(cart_id=cart.id, product_id=product.id, quantity=1, unit_price_amount=product.price_amount))
                total_abandoned_carts += 1

        # A slice of fully anonymous abandoned carts (no customer_id) —
        # browsing sessions that never even created an account/order.
        for _ in range(60):
            cart_date = sample_order_date(0, LOOKBACK_DAYS, True)
            cart = Cart(
                merchant_id=merchant.id,
                customer_id=None,
                session_ref=f"anon_{uuid.uuid4().hex[:12]}",
                status="abandoned",
                created_at=cart_date,
                updated_at=cart_date,
            )
            db.add(cart)
            db.flush()
            basket = build_basket(products, affinity_map, (1, 2))
            for product in basket:
                db.add(CartItem(cart_id=cart.id, product_id=product.id, quantity=1, unit_price_amount=product.price_amount))
            total_abandoned_carts += 1

        db.commit()

        print("\n--- Seed summary ---")
        print(f"Merchant:          TechNest ({merchant.id})")
        print(f"Demo login:        owner@technest.demo / RevPilotDemo123!")
        print(f"Products:          {len(products)}")
        print(f"Customers:         {len(customers)}")
        print(f"Orders:            {total_orders}")
        print(f"Paid revenue:      Rs. {total_paid_revenue:,.2f}")
        print(f"Abandoned carts:   {total_abandoned_carts}")
        print("Done.")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main(reset=True)

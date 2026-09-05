"""Lets a merchant upload their own customer/order history (CSV) for
analysis, instead of only ever seeing RevPilot's seeded demo data.

Every row is validated before any DB write, and each file's import
commits as a single transaction (or nothing does) — a malformed row
anywhere in the middle of a large file is reported and skipped, not
allowed to leave the database half-written. After a successful orders
import, the full deterministic analytics pipeline (RFM, affinity,
opportunity detection/scoring — see app/opportunities/service.py) is
re-run automatically against the merchant's combined dataset, so new
opportunities reflect the uploaded data immediately. Nothing here
touches payments, campaigns, or any financial action — this is
strictly a data-ingestion path for the deterministic analytics engine.
"""
import csv
import io
import uuid
from datetime import timezone,  datetime
UTC = timezone.utc

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.catalog import Product
from app.models.commerce import Order, OrderItem
from app.models.customers import Customer
from app.models.ops import AuditLog
from app.opportunities.service import run_full_analytics

MAX_ROWS = 20_000
VALID_ORDER_STATUSES = {"paid", "pending", "failed", "cancelled", "refunded"}

CUSTOMERS_CSV_COLUMNS = ["name (required)", "email", "phone", "external_ref"]
ORDERS_CSV_COLUMNS = [
    "customer_email (required)", "total_amount (required)", "status (required: paid|pending|failed|cancelled|refunded)",
    "created_at (required, ISO date e.g. 2026-01-15)", "product_skus (optional, ';'-separated, must match existing catalog SKUs)",
]


def _audit(db: Session, merchant_id: uuid.UUID, action: str, result: str, input_summary: str, error: str | None = None) -> None:
    db.add(AuditLog(
        merchant_id=merchant_id, action=action, tool="data_import", input_summary=input_summary[:1000],
        result=result, error=error, created_at=datetime.now(UTC),
    ))


def _read_rows(raw_bytes: bytes, required_columns: set[str]) -> list[dict]:
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError("INVALID_CSV", "File is not valid UTF-8 text. Please upload a plain CSV file.", status_code=422) from exc

    reader = csv.DictReader(io.StringIO(text))
    fieldnames = {f.strip().lower() for f in (reader.fieldnames or [])}
    missing = required_columns - fieldnames
    if missing:
        raise AppError(
            "INVALID_CSV", f"CSV is missing required column(s): {', '.join(sorted(missing))}.", status_code=422,
        )

    rows = [{k.strip().lower(): (v or "").strip() for k, v in row.items()} for row in reader]
    if len(rows) > MAX_ROWS:
        raise AppError("FILE_TOO_LARGE", f"Cannot import more than {MAX_ROWS:,} rows in a single upload.", status_code=413)
    return rows


def import_customers_csv(db: Session, merchant_id: uuid.UUID, raw_bytes: bytes) -> dict:
    rows = _read_rows(raw_bytes, required_columns={"name"})

    created, matched, skipped = 0, 0, []
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        name = row.get("name")
        email = row.get("email") or None
        if not name:
            skipped.append({"row": i, "reason": "missing 'name'"})
            continue

        existing = None
        if email:
            existing = db.query(Customer).filter(Customer.merchant_id == merchant_id, Customer.email == email).first()
        if existing is not None:
            matched += 1
            continue

        db.add(Customer(
            merchant_id=merchant_id, name=name, email=email,
            phone=row.get("phone") or None, external_ref=row.get("external_ref") or None,
        ))
        created += 1

    db.flush()
    _audit(db, merchant_id, "IMPORT_CUSTOMERS_CSV", "success", f"{created} created, {matched} matched to existing, {len(skipped)} skipped")
    db.commit()
    return {"customers_created": created, "customers_matched_existing": matched, "rows_skipped": skipped}


def import_orders_csv(db: Session, merchant_id: uuid.UUID, raw_bytes: bytes) -> dict:
    rows = _read_rows(raw_bytes, required_columns={"customer_email", "total_amount", "status", "created_at"})

    products_by_sku = {p.sku: p for p in db.query(Product).filter(Product.merchant_id == merchant_id).all()}
    created, skipped = 0, []

    try:
        for i, row in enumerate(rows, start=2):
            email = row.get("customer_email")
            status = row.get("status", "").lower()

            try:
                total_amount = float(row.get("total_amount", ""))
            except ValueError:
                skipped.append({"row": i, "reason": "'total_amount' is not a number"})
                continue

            if not email:
                skipped.append({"row": i, "reason": "missing 'customer_email'"})
                continue
            if status not in VALID_ORDER_STATUSES:
                skipped.append({"row": i, "reason": f"'status' must be one of {sorted(VALID_ORDER_STATUSES)}"})
                continue
            if total_amount < 0:
                skipped.append({"row": i, "reason": "'total_amount' cannot be negative"})
                continue

            try:
                created_at = datetime.fromisoformat(row["created_at"])
            except ValueError:
                skipped.append({"row": i, "reason": "'created_at' must be an ISO date, e.g. 2026-01-15"})
                continue
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)

            customer = db.query(Customer).filter(Customer.merchant_id == merchant_id, Customer.email == email).first()
            if customer is None:
                customer = Customer(merchant_id=merchant_id, name=email.split("@")[0], email=email)
                db.add(customer)
                db.flush()

            order = Order(
                merchant_id=merchant_id, customer_id=customer.id, status=status,
                subtotal_amount=total_amount, discount_amount=0, shipping_amount=0, total_amount=total_amount,
                source="imported", created_at=created_at,
            )
            db.add(order)
            db.flush()

            skus = [s.strip() for s in row.get("product_skus", "").split(";") if s.strip()]
            for sku in skus:
                product = products_by_sku.get(sku)
                if product is not None:
                    db.add(OrderItem(order_id=order.id, product_id=product.id, quantity=1, unit_price_amount=product.price_amount))
                # An unrecognized SKU does not fail the row -- the order's
                # total is still real and imported, just without a
                # line-item breakdown for that product. This mirrors real
                # merchant exports, which often reference SKUs from a
                # POS system RevPilot's catalog doesn't have yet.

            if status == "paid":
                customer.total_spend = float(customer.total_spend or 0) + total_amount
                customer.order_count = (customer.order_count or 0) + 1
                if customer.last_order_at is None or created_at > customer.last_order_at:
                    customer.last_order_at = created_at
                if customer.first_order_at is None or created_at < customer.first_order_at:
                    customer.first_order_at = created_at

            created += 1
    except Exception as exc:
        db.rollback()
        _audit(db, merchant_id, "IMPORT_ORDERS_CSV", "failed", f"import aborted after {created} rows", error=str(exc))
        db.commit()
        raise AppError("IMPORT_FAILED", f"Import aborted, no rows were written: {exc}", status_code=422) from exc

    _audit(db, merchant_id, "IMPORT_ORDERS_CSV", "success", f"{created} created, {len(skipped)} skipped")
    db.commit()

    analytics = run_full_analytics(db, merchant_id)
    return {
        "orders_created": created,
        "rows_skipped": skipped,
        "analytics_refreshed": {
            "opportunities_detected": analytics["opportunities_detected"],
            "opportunities_by_type": analytics["opportunities_by_type"],
        },
    }

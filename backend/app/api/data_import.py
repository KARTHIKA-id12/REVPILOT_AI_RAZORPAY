"""Lets a merchant upload their own customer/order history for real
analysis. Restricted to OWNER/ADMIN, matching the restriction used for
settings changes and approvals — this mutates a merchant's core dataset
and triggers a full analytics recompute, so it is not a passive read.
"""
import uuid

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.security.auth import Principal, ensure_merchant_access, get_principal
from app.services.data_import import CUSTOMERS_CSV_COLUMNS, ORDERS_CSV_COLUMNS, import_customers_csv, import_orders_csv

router = APIRouter(prefix="/api/v1/data", tags=["data-import"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB — generous for a CSV, small enough to reject an accidental wrong-file upload fast


async def _read_upload(file: UploadFile) -> bytes:
    if file.content_type not in ("text/csv", "application/vnd.ms-excel", "application/octet-stream", "text/plain", None):
        raise AppError("INVALID_FILE_TYPE", "Please upload a .csv file.", status_code=422)
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise AppError("FILE_TOO_LARGE", f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.", status_code=413)
    if not raw:
        raise AppError("EMPTY_FILE", "The uploaded file is empty.", status_code=422)
    return raw


@router.get("/schema")
def upload_schema():
    """Machine-readable description of the expected CSV columns, so the
    frontend (or a merchant's own script) can build a conforming file
    without guessing."""
    return {
        "customers_csv": {"required_or_optional_columns": CUSTOMERS_CSV_COLUMNS},
        "orders_csv": {"required_or_optional_columns": ORDERS_CSV_COLUMNS},
    }


@router.post("/upload/customers")
async def upload_customers(
    merchant_id: uuid.UUID,
    file: UploadFile,
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    ensure_merchant_access(db, merchant_id, principal, allowed_roles={"OWNER", "ADMIN"})
    raw = await _read_upload(file)
    return import_customers_csv(db, merchant_id, raw)


@router.post("/upload/orders")
async def upload_orders(
    merchant_id: uuid.UUID,
    file: UploadFile,
    principal: Principal | None = Depends(get_principal),
    db: Session = Depends(get_db),
):
    """Importing orders also re-runs the full deterministic analytics
    pipeline (RFM, affinity, opportunity detection) automatically — the
    response includes a fresh opportunity count reflecting the newly
    uploaded data, not a cached figure."""
    ensure_merchant_access(db, merchant_id, principal, allowed_roles={"OWNER", "ADMIN"})
    raw = await _read_upload(file)
    return import_orders_csv(db, merchant_id, raw)

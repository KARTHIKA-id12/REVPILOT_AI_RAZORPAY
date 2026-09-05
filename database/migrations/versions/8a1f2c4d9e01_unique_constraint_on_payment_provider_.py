"""unique constraint on payment provider_order_id

Found during a full-project audit: provider_payment_link_id and
idempotency_key were already protected by a DB-level unique constraint,
but provider_order_id (used by the direct Razorpay Order + AI Buyer
checkout flow, see app/checkout/service.py and the order.paid webhook
handler) was not. The application-level idempotency_key check already
prevents duplicate Payment rows in the common case, but a DB-level
constraint closes the remaining race-condition window (two concurrent
requests both passing the idempotency check before either commits) and
matches the defense-in-depth pattern already used for
provider_payment_link_id. NULLs remain unrestricted (Postgres does not
treat NULL = NULL for uniqueness), so mock/campaign payments that never
set provider_order_id are unaffected.

Revision ID: 8a1f2c4d9e01
Revises: 6c1f8d1a2e4b
Create Date: 2026-09-04 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8a1f2c4d9e01"
down_revision: Union[str, None] = "6c1f8d1a2e4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("uq_payment_provider_order_id", "payments", ["provider_order_id"])


def downgrade() -> None:
    op.drop_constraint("uq_payment_provider_order_id", "payments", type_="unique")

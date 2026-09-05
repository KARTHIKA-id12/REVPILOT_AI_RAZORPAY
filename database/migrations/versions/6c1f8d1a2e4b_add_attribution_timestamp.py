"""add attribution timestamp

Revision ID: 6c1f8d1a2e4b
Revises: 295f33c8efc3
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6c1f8d1a2e4b"
down_revision: Union[str, None] = "295f33c8efc3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "revenue_attributions",
        sa.Column("attribution_timestamp", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    )
    op.execute("UPDATE revenue_attributions SET attribution_timestamp = created_at WHERE attribution_timestamp IS NULL")
    op.alter_column("revenue_attributions", "attribution_timestamp", nullable=False, server_default=None)
    op.create_unique_constraint("uq_revenue_attribution_payment_id", "revenue_attributions", ["payment_id"])


def downgrade() -> None:
    op.drop_constraint("uq_revenue_attribution_payment_id", "revenue_attributions", type_="unique")
    op.drop_column("revenue_attributions", "attribution_timestamp")
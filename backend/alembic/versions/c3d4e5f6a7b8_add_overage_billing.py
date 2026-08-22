"""add usage-based overage billing columns

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-22 15:00:00.000000

Two columns enable per-GB surcharge billing:

- ``plans.overage_price_per_gb`` — the per-GB rate charged for consumption
  beyond a plan's quota (NULL = no surcharge; a quota cap alone never bills).
- ``invoices.kind`` — distinguishes the monthly base invoice from a usage
  overage surcharge, so overage generation can be idempotent per
  (subscriber, period) without colliding with the base-invoice overlap
  check, and so the dashboard can badge surcharges.

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column("overage_price_per_gb", sa.Numeric(10, 2), nullable=True),
    )
    # Existing invoices are all monthly base bills.
    op.add_column(
        "invoices",
        sa.Column(
            "kind",
            sa.String(16),
            server_default="base",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("invoices", "kind")
    op.drop_column("plans", "overage_price_per_gb")

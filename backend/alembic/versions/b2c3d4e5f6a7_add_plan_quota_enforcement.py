"""add plans.enforce_quota (opt-in over-quota enforcement)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-22 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Opt-in: enforcement stays off for every existing plan until an operator
    # flips the toggle — a quota cap alone never disconnects subscribers.
    op.add_column(
        "plans",
        sa.Column(
            "enforce_quota",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("plans", "enforce_quota")

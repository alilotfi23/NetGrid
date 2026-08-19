"""add nas device ports/server/community fields

Revision ID: 7d1a2f3c4b5a
Revises: 599cf800e448
Create Date: 2026-08-19 07:30:00.000000

Phase 7 (NAS devices): the FreeRADIUS nas table carries ports, server, and
community columns, so nas_devices gains them for the same-transaction sync.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7d1a2f3c4b5a"
down_revision: str | Sequence[str] | None = "599cf800e448"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nas-table-mirrored columns to nas_devices."""
    op.add_column("nas_devices", sa.Column("ports", sa.Integer(), nullable=True))
    op.add_column("nas_devices", sa.Column("server", sa.String(length=64), nullable=True))
    op.add_column("nas_devices", sa.Column("community", sa.String(length=50), nullable=True))


def downgrade() -> None:
    """Drop the columns."""
    op.drop_column("nas_devices", "community")
    op.drop_column("nas_devices", "server")
    op.drop_column("nas_devices", "ports")

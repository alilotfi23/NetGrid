"""add usage:read permission code

Revision ID: a1b2c3d4e5f6
Revises: 8a1b2c3d4e5f
Create Date: 2026-08-22 12:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "8a1b2c3d4e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The data-cap usage report endpoint (current-month consumption vs plan
# quota). super_admin (via *:*) and auditor (via *:read) inherit this through
# their wildcard grants, so no role links are needed here — the row exists so
# the code is assignable to custom roles and listable in the permission catalog.
NEW_PERMISSIONS = [
    ("usage:read", "View subscriber data-cap usage"),
]

permissions = sa.table(
    "permissions",
    sa.column("id", sa.Integer),
    sa.column("code", sa.String),
    sa.column("description", sa.String),
)
role_permissions = sa.table(
    "role_permissions",
    sa.column("role_id", sa.Integer),
    sa.column("permission_id", sa.Integer),
)


def _get_or_create_id(conn, table, id_col, match_col, value, **insert_values) -> int:
    existing = conn.execute(sa.select(id_col).where(match_col == value)).scalar_one_or_none()
    if existing is not None:
        return int(existing)
    return int(
        conn.execute(sa.insert(table).values(**insert_values).returning(id_col)).scalar_one()
    )


def upgrade() -> None:
    """Seed the usage read permission code (get-or-create)."""
    conn = op.get_bind()
    for code, description in NEW_PERMISSIONS:
        _get_or_create_id(
            conn,
            permissions,
            permissions.c.id,
            permissions.c.code,
            code,
            code=code,
            description=description,
        )


def downgrade() -> None:
    """Remove the seeded code and any links to it."""
    conn = op.get_bind()
    for code, _ in NEW_PERMISSIONS:
        perm_id = conn.execute(
            sa.select(permissions.c.id).where(permissions.c.code == code)
        ).scalar_one_or_none()
        if perm_id is not None:
            conn.execute(
                sa.delete(role_permissions).where(role_permissions.c.permission_id == perm_id)
            )
            conn.execute(sa.delete(permissions).where(permissions.c.id == perm_id))

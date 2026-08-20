"""add audit_logs:read permission code

Revision ID: 8a1b2c3d4e5f
Revises: 7d1a2f3c4b5a
Create Date: 2026-08-20 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8a1b2c3d4e5f"
down_revision: str | Sequence[str] | None = "7d1a2f3c4b5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The audit log read endpoint, added with the Phase 12 dashboard viewer.
# super_admin (via *:*) and auditor (via *:read) inherit this through their
# wildcard grants, so no role links are needed here — the row exists so the
# code is assignable to custom roles and listable in the permission catalog.
NEW_PERMISSIONS = [
    ("audit_logs:read", "View the admin audit trail"),
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
    """Seed the audit log read permission code (get-or-create)."""
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

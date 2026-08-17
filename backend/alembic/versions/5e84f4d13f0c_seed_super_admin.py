"""seed super admin

Revision ID: 5e84f4d13f0c
Revises: a28cbe094ce8
Create Date: 2026-08-17 22:01:17.183121

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5e84f4d13f0c"
down_revision: str | Sequence[str] | None = "a28cbe094ce8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ---------------------------------------------------------------------------
# Dev bootstrap. CHANGE THE PASSWORD after first login:
#   username: superadmin
#   password: netgrid-admin
# The hash below is the argon2id of "netgrid-admin" (passlib/argon2-cffi).
# ---------------------------------------------------------------------------
SUPERADMIN_USERNAME = "superadmin"
SUPERADMIN_EMAIL = "superadmin@netgrid.local"
SUPERADMIN_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$RWhtjXFOybnXuleqda611g"
    "$DGef6aByEvHPvuF0hbNL+JjX7e/1UIHhn2MV+RyKiMA"
)

SUPERADMIN_ROLE = "super_admin"
SUPERADMIN_ROLE_DESC = "Full access to all NetGrid resources"

# Every permission currently defined in CLAUDE.md's RBAC model.
PERMISSIONS = [
    "subscribers:read",
    "subscribers:write",
    "subscribers:delete",
    "plans:read",
    "plans:write",
    "invoices:read",
    "invoices:write",
    "nas_devices:read",
    "nas_devices:write",
    "sessions:read",
    "sessions:disconnect",
    "admins:manage",
]

# Lightweight table views for this migration only — never import app models
# here (model changes must not break historical migrations).
admins = sa.table(
    "admins",
    sa.column("id", sa.Integer),
    sa.column("username", sa.String),
    sa.column("email", sa.String),
    sa.column("password_hash", sa.String),
    sa.column("is_active", sa.Boolean),
)
roles = sa.table(
    "roles",
    sa.column("id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("description", sa.String),
)
permissions = sa.table(
    "permissions",
    sa.column("id", sa.Integer),
    sa.column("code", sa.String),
)
admin_roles = sa.table(
    "admin_roles",
    sa.column("admin_id", sa.Integer),
    sa.column("role_id", sa.Integer),
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
    """Seed the super_admin role, all permissions, and the bootstrap admin."""
    conn = op.get_bind()

    role_id = _get_or_create_id(
        conn,
        roles,
        roles.c.id,
        roles.c.name,
        SUPERADMIN_ROLE,
        name=SUPERADMIN_ROLE,
        description=SUPERADMIN_ROLE_DESC,
    )

    perm_ids: list[int] = []
    for code in PERMISSIONS:
        perm_id = _get_or_create_id(
            conn, permissions, permissions.c.id, permissions.c.code, code, code=code
        )
        perm_ids.append(perm_id)
        conn.execute(
            pg_insert(role_permissions)
            .values(role_id=role_id, permission_id=perm_id)
            .on_conflict_do_nothing()
        )

    admin_id = _get_or_create_id(
        conn,
        admins,
        admins.c.id,
        admins.c.username,
        SUPERADMIN_USERNAME,
        username=SUPERADMIN_USERNAME,
        email=SUPERADMIN_EMAIL,
        password_hash=SUPERADMIN_PASSWORD_HASH,
        is_active=True,
    )
    conn.execute(
        pg_insert(admin_roles).values(admin_id=admin_id, role_id=role_id).on_conflict_do_nothing()
    )


def downgrade() -> None:
    """Remove the seeded admin, links, permissions, and role (in FK order)."""
    conn = op.get_bind()

    admin_id = conn.execute(
        sa.select(admins.c.id).where(admins.c.username == SUPERADMIN_USERNAME)
    ).scalar_one_or_none()
    role_id = conn.execute(
        sa.select(roles.c.id).where(roles.c.name == SUPERADMIN_ROLE)
    ).scalar_one_or_none()

    if admin_id is not None:
        if role_id is not None:
            conn.execute(
                sa.delete(admin_roles).where(
                    admin_roles.c.admin_id == admin_id, admin_roles.c.role_id == role_id
                )
            )
        conn.execute(sa.delete(admins).where(admins.c.id == admin_id))

    if role_id is not None:
        for code in PERMISSIONS:
            perm_id = conn.execute(
                sa.select(permissions.c.id).where(permissions.c.code == code)
            ).scalar_one_or_none()
            if perm_id is not None:
                conn.execute(
                    sa.delete(role_permissions).where(role_permissions.c.permission_id == perm_id)
                )
                conn.execute(sa.delete(permissions).where(permissions.c.id == perm_id))
        conn.execute(sa.delete(roles).where(roles.c.id == role_id))

"""add auditor and wildcard permissions

Revision ID: 09e98b342160
Revises: 5e84f4d13f0c
Create Date: 2026-08-17 22:15:36.468807

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert as pg_insert

# revision identifiers, used by Alembic.
revision: str = "09e98b342160"
down_revision: Union[str, Sequence[str], None] = "5e84f4d13f0c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUDITOR_ROLE = "auditor"
AUDITOR_ROLE_DESC = "Read-only access to all NetGrid resources"
WILDCARD_READ = "*:read"
WILDCARD_ALL = "*:*"
SUPERADMIN_ROLE = "super_admin"

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
role_permissions = sa.table(
    "role_permissions",
    sa.column("role_id", sa.Integer),
    sa.column("permission_id", sa.Integer),
)


def _get_or_create_id(conn, table, id_col, match_col, value, **insert_values) -> int:
    existing = conn.execute(sa.select(id_col).where(match_col == value)).scalar_one_or_none()
    if existing is not None:
        return int(existing)
    return int(conn.execute(sa.insert(table).values(**insert_values).returning(id_col)).scalar_one())


def _link(conn, role_id: int, permission_id: int) -> None:
    conn.execute(
        pg_insert(role_permissions)
        .values(role_id=role_id, permission_id=permission_id)
        .on_conflict_do_nothing()
    )


def upgrade() -> None:
    """Seed the auditor role and wildcard permissions; make super_admin use *:*."""
    conn = op.get_bind()

    read_id = _get_or_create_id(
        conn, permissions, permissions.c.id, permissions.c.code, WILDCARD_READ, code=WILDCARD_READ
    )
    all_id = _get_or_create_id(
        conn, permissions, permissions.c.id, permissions.c.code, WILDCARD_ALL, code=WILDCARD_ALL
    )

    auditor_id = _get_or_create_id(
        conn,
        roles,
        roles.c.id,
        roles.c.name,
        AUDITOR_ROLE,
        name=AUDITOR_ROLE,
        description=AUDITOR_ROLE_DESC,
    )
    _link(conn, auditor_id, read_id)

    super_admin_id = conn.execute(
        sa.select(roles.c.id).where(roles.c.name == SUPERADMIN_ROLE)
    ).scalar_one_or_none()
    if super_admin_id is not None:
        _link(conn, int(super_admin_id), all_id)


def downgrade() -> None:
    """Remove the auditor role, wildcard permissions, and super_admin's *:* link."""
    conn = op.get_bind()

    auditor_id = conn.execute(
        sa.select(roles.c.id).where(roles.c.name == AUDITOR_ROLE)
    ).scalar_one_or_none()
    if auditor_id is not None:
        conn.execute(sa.delete(role_permissions).where(role_permissions.c.role_id == auditor_id))
        conn.execute(sa.delete(roles).where(roles.c.id == auditor_id))

    for code in (WILDCARD_READ, WILDCARD_ALL):
        perm_id = conn.execute(
            sa.select(permissions.c.id).where(permissions.c.code == code)
        ).scalar_one_or_none()
        if perm_id is not None:
            conn.execute(
                sa.delete(role_permissions).where(role_permissions.c.permission_id == perm_id)
            )
            conn.execute(sa.delete(permissions).where(permissions.c.id == perm_id))

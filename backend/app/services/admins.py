"""Admin and role management service (Phase 3 remainder).

All mutations are gated upstream by require_permission(...); this layer
enforces the self-protection invariants (nobody may strip their own
admins:manage access), invalidates the affected admins' permission cache,
and writes audit entries for every change.
"""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.rbac import has_permission
from app.core.security import hash_password
from app.models.rbac import Admin, Permission, Role, admin_roles
from app.services import audit as audit_service
from app.services.rbac import get_permission_state, invalidate_admin_permissions

ADMINS_MANAGE = "admins:manage"


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


async def list_admins(session: AsyncSession, page: int, page_size: int) -> tuple[list[Admin], int]:
    total = (await session.execute(select(func.count()).select_from(Admin))).scalar_one()
    result = await session.execute(
        select(Admin)
        .options(selectinload(Admin.roles))
        .order_by(Admin.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), int(total)


async def get_admin_or_404(session: AsyncSession, admin_id: int) -> Admin:
    admin = (
        await session.execute(
            select(Admin).options(selectinload(Admin.roles)).where(Admin.id == admin_id)
        )
    ).scalar_one_or_none()
    if admin is None:
        raise NotFoundError("Admin not found")
    return admin


async def list_roles(session: AsyncSession) -> list[Role]:
    result = await session.execute(
        select(Role).options(selectinload(Role.permissions)).order_by(Role.id)
    )
    return list(result.scalars().all())


async def get_role_or_404(session: AsyncSession, role_id: int) -> Role:
    role = (
        await session.execute(
            select(Role).options(selectinload(Role.permissions)).where(Role.id == role_id)
        )
    ).scalar_one_or_none()
    if role is None:
        raise NotFoundError("Role not found")
    return role


async def list_permissions(session: AsyncSession) -> list[Permission]:
    result = await session.execute(select(Permission).order_by(Permission.code))
    return list(result.scalars().all())


async def _roles_by_ids(session: AsyncSession, role_ids: list[int]) -> list[Role]:
    if not role_ids:
        return []
    result = await session.execute(select(Role).where(Role.id.in_(role_ids)))
    roles = list(result.scalars().all())
    if len(roles) != len(set(role_ids)):
        raise NotFoundError("One or more roles not found")
    return roles


async def _permissions_by_codes(session: AsyncSession, codes: list[str]) -> list[Permission]:
    if not codes:
        return []
    result = await session.execute(select(Permission).where(Permission.code.in_(codes)))
    permissions = list(result.scalars().all())
    if len(permissions) != len(set(codes)):
        raise NotFoundError("One or more permissions not found")
    return permissions


async def _role_member_ids(session: AsyncSession, role_id: int) -> list[int]:
    result = await session.execute(
        select(admin_roles.c.admin_id).where(admin_roles.c.role_id == role_id)
    )
    return [int(admin_id) for admin_id in result.scalars().all()]


async def _commit_or_conflict(session: AsyncSession, message: str) -> None:
    """Commit, mapping unique-constraint violations to ConflictError."""
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(message) from None


# ---------------------------------------------------------------------------
# Admin mutations
# ---------------------------------------------------------------------------


async def create_admin(
    session: AsyncSession,
    *,
    username: str,
    email: str,
    password: str,
    is_active: bool,
    role_ids: list[int],
    actor_id: int,
) -> Admin:
    roles = await _roles_by_ids(session, role_ids)
    admin = Admin(
        username=username,
        email=email,
        password_hash=hash_password(password),
        is_active=is_active,
        roles=roles,
    )
    session.add(admin)
    await _commit_or_conflict(session, "Username or email already in use")
    await audit_service.record_audit(
        session,
        admin_id=actor_id,
        action="create",
        resource="admins",
        resource_id=str(admin.id),
        metadata_={"username": admin.username, "email": admin.email, "role_ids": role_ids},
    )
    return admin


async def update_admin(
    session: AsyncSession,
    admin: Admin,
    *,
    actor_id: int,
    username: str | None = None,
    email: str | None = None,
    password: str | None = None,
    is_active: bool | None = None,
) -> Admin:
    if admin.id == actor_id and is_active is False:
        raise BadRequestError("Cannot deactivate yourself")

    changed: list[str] = []
    if username is not None and username != admin.username:
        admin.username = username
        changed.append("username")
    if email is not None and email != admin.email:
        admin.email = email
        changed.append("email")
    if password is not None:
        admin.password_hash = hash_password(password)
        changed.append("password")
    if is_active is not None and is_active != admin.is_active:
        admin.is_active = is_active
        changed.append("is_active")

    if changed:
        await _commit_or_conflict(session, "Username or email already in use")
        await audit_service.record_audit(
            session,
            admin_id=actor_id,
            action="update",
            resource="admins",
            resource_id=str(admin.id),
            metadata_={"fields": changed},
        )
    return admin


async def set_admin_roles(
    session: AsyncSession, admin: Admin, role_ids: list[int], actor_id: int
) -> Admin:
    if admin.id == actor_id:
        raise BadRequestError("Cannot change your own roles")
    admin.roles = await _roles_by_ids(session, role_ids)
    await session.commit()
    await invalidate_admin_permissions(admin.id)
    await audit_service.record_audit(
        session,
        admin_id=actor_id,
        action="assign_roles",
        resource="admins",
        resource_id=str(admin.id),
        metadata_={"role_ids": role_ids},
    )
    return admin


# ---------------------------------------------------------------------------
# Role mutations
# ---------------------------------------------------------------------------


async def create_role(
    session: AsyncSession,
    *,
    name: str,
    description: str | None,
    permission_codes: list[str],
    actor_id: int,
) -> Role:
    permissions = await _permissions_by_codes(session, permission_codes)
    role = Role(name=name, description=description, permissions=permissions)
    session.add(role)
    await _commit_or_conflict(session, "Role name already exists")
    await audit_service.record_audit(
        session,
        admin_id=actor_id,
        action="create",
        resource="roles",
        resource_id=str(role.id),
        metadata_={"name": role.name, "permission_codes": permission_codes},
    )
    return role


async def update_role(
    session: AsyncSession,
    role: Role,
    *,
    actor_id: int,
    name: str | None = None,
    description: str | None = None,
) -> Role:
    changed: list[str] = []
    if name is not None and name != role.name:
        role.name = name
        changed.append("name")
    if description is not None and description != role.description:
        role.description = description
        changed.append("description")

    if changed:
        await _commit_or_conflict(session, "Role name already exists")
        await audit_service.record_audit(
            session,
            admin_id=actor_id,
            action="update",
            resource="roles",
            resource_id=str(role.id),
            metadata_={"fields": changed},
        )
    return role


async def set_role_permissions(
    session: AsyncSession, role: Role, permission_codes: list[str], actor_id: int
) -> Role:
    """Replace a role's permission set, then invalidate every member's cache.

    Self-protection: if the acting admin holds this role, the edit must not
    strip their own admins:manage access — that is the classic lockout path
    (an admin removing *:* from their own super_admin role).
    """
    new_permissions = await _permissions_by_codes(session, permission_codes)

    state = await get_permission_state(session, actor_id)
    if has_permission(state.codes, ADMINS_MANAGE):
        membership = await session.execute(
            select(admin_roles.c.admin_id).where(
                admin_roles.c.role_id == role.id, admin_roles.c.admin_id == actor_id
            )
        )
        if membership.scalar_one_or_none() is not None:
            new_codes = (set(state.codes) - {p.code for p in role.permissions}) | {
                p.code for p in new_permissions
            }
            if not has_permission(new_codes, ADMINS_MANAGE):
                raise BadRequestError("This change would remove your own admins:manage access")

    role.permissions = new_permissions
    await session.commit()
    for admin_id in await _role_member_ids(session, role.id):
        await invalidate_admin_permissions(admin_id)
    await audit_service.record_audit(
        session,
        admin_id=actor_id,
        action="update_permissions",
        resource="roles",
        resource_id=str(role.id),
        metadata_={"permission_codes": permission_codes},
    )
    return role

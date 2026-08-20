"""Audit trail for security-relevant events (audit_log table)."""

from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.rbac import Admin


class AuditFilterOptions(TypedDict):
    """Distinct filter values present in the log (actions, resources, actors)."""

    actions: list[str]
    resources: list[str]
    admins: list[tuple[int, str]]  # (admin_id, username)


async def record_audit(
    session: AsyncSession,
    *,
    admin_id: int | None,
    action: str,
    resource: str,
    resource_id: str | None = None,
    metadata_: dict[str, object] | None = None,
) -> AuditLog:
    """Persist one audit entry and commit, so the trail survives immediately."""
    entry = AuditLog(
        admin_id=admin_id,
        action=action,
        resource=resource,
        resource_id=resource_id,
        metadata_=metadata_,
    )
    session.add(entry)
    await session.commit()
    return entry


async def record_login_success(session: AsyncSession, admin: Admin, ip: str | None) -> AuditLog:
    return await record_audit(
        session,
        admin_id=admin.id,
        action="login",
        resource="auth",
        metadata_={"ip": ip} if ip is not None else None,
    )


async def record_login_failure(session: AsyncSession, username: str, ip: str | None) -> AuditLog:
    metadata_: dict[str, object] = {"username": username}
    if ip is not None:
        metadata_["ip"] = ip
    return await record_audit(
        session,
        admin_id=None,
        action="login_failed",
        resource="auth",
        metadata_=metadata_,
    )


async def record_permission_denied(
    session: AsyncSession, admin_id: int, permission: str, path: str
) -> AuditLog:
    return await record_audit(
        session,
        admin_id=admin_id,
        action="permission_denied",
        resource="rbac",
        metadata_={"permission": permission, "path": path},
    )


# ---------------------------------------------------------------------------
# Read side (Phase 12 audit log viewer)
# ---------------------------------------------------------------------------


async def list_audit_logs(
    session: AsyncSession,
    page: int,
    page_size: int,
    *,
    admin_id: int | None = None,
    action: str | None = None,
    resource: str | None = None,
) -> tuple[list[AuditLog], int]:
    """Paginated audit trail, newest first; filters on actor/action/resource."""
    count_stmt = select(func.count()).select_from(AuditLog)
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    if admin_id is not None:
        count_stmt = count_stmt.where(AuditLog.admin_id == admin_id)
        stmt = stmt.where(AuditLog.admin_id == admin_id)
    if action is not None:
        count_stmt = count_stmt.where(AuditLog.action == action)
        stmt = stmt.where(AuditLog.action == action)
    if resource is not None:
        count_stmt = count_stmt.where(AuditLog.resource == resource)
        stmt = stmt.where(AuditLog.resource == resource)
    total = (await session.execute(count_stmt)).scalar_one()
    result = await session.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    return list(result.scalars().all()), int(total)


async def get_admin_usernames(session: AsyncSession, ids: list[int]) -> dict[int, str]:
    """Map admin id -> username for the API layer's display fields."""
    if not ids:
        return {}
    rows = (
        await session.execute(select(Admin.id, Admin.username).where(Admin.id.in_(ids)))
    ).all()
    return {admin_id: username for admin_id, username in rows}


async def get_audit_log_filter_options(session: AsyncSession) -> AuditFilterOptions:
    """Distinct filter values present in the log, for the dashboard dropdowns.

    The admin list contains only admins who actually appear as an actor in
    the trail, so the actor filter never offers dead options.
    """
    actions = (
        (await session.execute(select(AuditLog.action).distinct().order_by(AuditLog.action)))
        .scalars()
        .all()
    )
    resources = (
        (await session.execute(select(AuditLog.resource).distinct().order_by(AuditLog.resource)))
        .scalars()
        .all()
    )
    actor_ids = [
        admin_id
        for admin_id in (
            await session.execute(
                select(AuditLog.admin_id).distinct().where(AuditLog.admin_id.is_not(None))
            )
        ).scalars()
        if admin_id is not None
    ]
    admins: list[tuple[int, str]] = []
    if actor_ids:
        rows = (
            await session.execute(
                select(Admin.id, Admin.username)
                .where(Admin.id.in_(actor_ids))
                .order_by(Admin.username)
            )
        ).all()
        admins = [(admin_id, username) for admin_id, username in rows]
    return {"actions": list(actions), "resources": list(resources), "admins": admins}

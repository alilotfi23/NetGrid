"""Audit trail for security-relevant events (audit_log table)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.rbac import Admin


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

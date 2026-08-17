from app.core.security import hash_password
from app.models.rbac import Admin
from app.services import audit as audit_service


async def _seed_admin(session) -> Admin:
    admin = Admin(username="root", email="root@netgrid.local", password_hash=hash_password("x"))
    session.add(admin)
    await session.commit()
    return admin


async def test_record_audit_creates_entry(session):
    admin = await _seed_admin(session)
    entry = await audit_service.record_audit(
        session, admin_id=admin.id, action="test", resource="auth", metadata_={"k": "v"}
    )
    assert entry.action == "test"
    assert entry.resource == "auth"
    assert entry.admin_id == admin.id
    assert entry.metadata_ == {"k": "v"}


async def test_record_login_success(session):
    admin = await _seed_admin(session)
    entry = await audit_service.record_login_success(session, admin, "1.2.3.4")
    assert entry.action == "login"
    assert entry.resource == "auth"
    assert entry.admin_id == admin.id
    assert entry.metadata_ == {"ip": "1.2.3.4"}


async def test_record_login_failure(session):
    entry = await audit_service.record_login_failure(session, "ghost", "1.2.3.4")
    assert entry.action == "login_failed"
    assert entry.admin_id is None
    assert entry.metadata_ == {"username": "ghost", "ip": "1.2.3.4"}


async def test_record_permission_denied(session):
    admin = await _seed_admin(session)
    entry = await audit_service.record_permission_denied(
        session, admin.id, "admins:read", "/api/v1/auth/me"
    )
    assert entry.action == "permission_denied"
    assert entry.resource == "rbac"
    assert entry.metadata_ == {"permission": "admins:read", "path": "/api/v1/auth/me"}

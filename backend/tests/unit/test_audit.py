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


# ---------------------------------------------------------------------------
# Read side (Phase 12 audit log viewer)
# ---------------------------------------------------------------------------


async def _seed_two_admins(session):
    alice = Admin(
        username="alice", email="alice@netgrid.local", password_hash=hash_password("x")
    )
    bob = Admin(username="bob", email="bob@netgrid.local", password_hash=hash_password("x"))
    session.add_all([alice, bob])
    await session.commit()
    return alice, bob


async def test_list_audit_logs_filters_and_paginates(session):
    alice, bob = await _seed_two_admins(session)
    await audit_service.record_audit(session, admin_id=alice.id, action="create", resource="plans")
    await audit_service.record_audit(
        session, admin_id=alice.id, action="payment", resource="invoices"
    )
    await audit_service.record_audit(session, admin_id=bob.id, action="login", resource="auth")

    # newest first
    items, total = await audit_service.list_audit_logs(session, 1, 20)
    assert total == 3
    assert [entry.action for entry in items] == ["login", "payment", "create"]

    # filter by actor
    items, total = await audit_service.list_audit_logs(session, 1, 20, admin_id=alice.id)
    assert total == 2
    assert {entry.action for entry in items} == {"create", "payment"}

    # filter by action and resource
    items, total = await audit_service.list_audit_logs(session, 1, 20, action="login")
    assert total == 1
    assert items[0].admin_id == bob.id
    items, total = await audit_service.list_audit_logs(session, 1, 20, resource="invoices")
    assert total == 1
    assert items[0].action == "payment"

    # combined filters and pagination
    items, total = await audit_service.list_audit_logs(
        session, 1, 2, admin_id=alice.id, resource="plans"
    )
    assert total == 1
    assert len(items) == 1
    items, total = await audit_service.list_audit_logs(session, 2, 2)
    assert total == 3
    assert len(items) == 1


async def test_list_audit_logs_empty(session):
    items, total = await audit_service.list_audit_logs(session, 1, 20)
    assert items == []
    assert total == 0


async def test_get_admin_usernames_maps_ids(session):
    alice, bob = await _seed_two_admins(session)
    names = await audit_service.get_admin_usernames(session, [alice.id, bob.id, 999])
    assert names == {alice.id: "alice", bob.id: "bob"}
    assert await audit_service.get_admin_usernames(session, []) == {}


async def test_get_audit_log_filter_options(session):
    alice, bob = await _seed_two_admins(session)
    await audit_service.record_audit(session, admin_id=alice.id, action="create", resource="plans")
    await audit_service.record_audit(session, admin_id=bob.id, action="login", resource="auth")
    # failed logins have no actor — they must not appear in the actor list
    await audit_service.record_audit(session, admin_id=None, action="login_failed", resource="auth")

    options = await audit_service.get_audit_log_filter_options(session)
    assert options["actions"] == ["create", "login", "login_failed"]
    assert options["resources"] == ["auth", "plans"]
    assert options["admins"] == [(alice.id, "alice"), (bob.id, "bob")]


async def test_get_audit_log_filter_options_empty(session):
    options = await audit_service.get_audit_log_filter_options(session)
    assert options == {"actions": [], "resources": [], "admins": []}

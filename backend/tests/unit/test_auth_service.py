import pytest

from app.core import security
from app.core.exceptions import UnauthorizedError
from app.core.security import hash_password
from app.models.rbac import Admin
from app.services import auth as auth_service


async def _seed_admin(session, username="root", password="secret123", is_active=True) -> Admin:
    admin = Admin(
        username=username,
        email=f"{username}@netgrid.local",
        password_hash=hash_password(password),
        is_active=is_active,
    )
    session.add(admin)
    await session.commit()
    return admin


async def test_authenticate_success(session):
    await _seed_admin(session)
    admin = await auth_service.authenticate_admin(session, "root", "secret123")
    assert admin.username == "root"


async def test_authenticate_wrong_password(session):
    await _seed_admin(session)
    with pytest.raises(UnauthorizedError):
        await auth_service.authenticate_admin(session, "root", "wrong")


async def test_authenticate_unknown_user(session):
    with pytest.raises(UnauthorizedError):
        await auth_service.authenticate_admin(session, "ghost", "secret123")


async def test_authenticate_inactive_admin(session):
    await _seed_admin(session, is_active=False)
    with pytest.raises(UnauthorizedError):
        await auth_service.authenticate_admin(session, "root", "secret123")


async def test_refresh_rotates_and_blacklists_old_token(session):
    admin = await _seed_admin(session)
    old_token, _ = security.create_refresh_token(str(admin.id))
    pair = await auth_service.refresh_tokens(session, old_token)
    assert pair["access_token"]
    assert pair["refresh_token"] != old_token
    with pytest.raises(UnauthorizedError):  # old token is now rotated away
        await auth_service.refresh_tokens(session, old_token)


async def test_refresh_rejects_garbage(session):
    await _seed_admin(session)
    with pytest.raises(UnauthorizedError):
        await auth_service.refresh_tokens(session, "not-a-token")


async def test_logout_blacklists_refresh_token(session):
    admin = await _seed_admin(session)
    token, _ = security.create_refresh_token(str(admin.id))
    await auth_service.logout(token)
    with pytest.raises(UnauthorizedError):
        await auth_service.refresh_tokens(session, token)

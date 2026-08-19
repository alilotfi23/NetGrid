"""NAS device service: inventory CRUD + direct FreeRADIUS nas-table coupling.

A NasDevice mirrors one row in FreeRADIUS's `nas` table, written in the same
transaction (CLAUDE.md direct-coupling decision): nasname is the device's
ip_address and secret is the *plaintext* shared secret — FreeRADIUS must
recover it for PAP/CHAP, so the encrypted copy (secret_encrypted, Fernet) is
the at-rest form in our table and the plaintext is what FreeRADIUS reads,
exactly like radcheck's Cleartext-Password. Deactivating a device removes its
nas row, so FreeRADIUS treats it as an unknown NAS and rejects it.
`ip_address` is immutable after creation (it is the RADIUS identity).
"""

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import decrypt_secret, encrypt_secret
from app.models.nas import NasDevice
from app.models.radius import Nas
from app.services import audit as audit_service


async def list_nas_devices(
    session: AsyncSession, page: int, page_size: int, q: str | None = None
) -> tuple[list[NasDevice], int]:
    """Paginated NAS inventory; `q` matches name or ip_address (case-insensitive)."""
    count_stmt = select(func.count()).select_from(NasDevice)
    stmt = select(NasDevice).order_by(NasDevice.id)
    if q:
        like = f"%{q}%"
        clause = or_(NasDevice.name.ilike(like), NasDevice.ip_address.ilike(like))
        count_stmt = count_stmt.where(clause)
        stmt = stmt.where(clause)
    total = (await session.execute(count_stmt)).scalar_one()
    result = await session.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    return list(result.scalars().all()), int(total)


async def get_nas_device_or_404(session: AsyncSession, nas_device_id: int) -> NasDevice:
    device = (
        await session.execute(select(NasDevice).where(NasDevice.id == nas_device_id))
    ).scalar_one_or_none()
    if device is None:
        raise NotFoundError("NAS device not found")
    return device


# ---------------------------------------------------------------------------
# FreeRADIUS nas-table sync
# ---------------------------------------------------------------------------


def _nas_values(device: NasDevice, plaintext_secret: str) -> dict[str, object]:
    """The nas-table columns a device's row should carry."""
    return {
        "nasname": device.ip_address,
        "shortname": device.shortname,
        "type": device.nas_type,
        "ports": device.ports,
        "secret": plaintext_secret,
        "server": device.server,
        "community": device.community,
        "description": device.description,
    }


async def _sync_nas_row(session: AsyncSession, device: NasDevice, plaintext_secret: str) -> None:
    """Upsert the device's nas row (active devices only)."""
    row = (
        await session.execute(select(Nas).where(Nas.nasname == device.ip_address))
    ).scalar_one_or_none()
    values = _nas_values(device, plaintext_secret)
    if row is None:
        session.add(Nas(**values))
    else:
        for column, value in values.items():
            setattr(row, column, value)


async def _remove_nas_row(session: AsyncSession, ip_address: str) -> None:
    await session.execute(delete(Nas).where(Nas.nasname == ip_address))


async def _commit_or_conflict(session: AsyncSession, message: str) -> None:
    """Commit, mapping unique-constraint violations to ConflictError."""
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(message) from None


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


async def create_nas_device(
    session: AsyncSession,
    *,
    actor_id: int,
    name: str,
    ip_address: str,
    shortname: str,
    secret: str,
    nas_type: str = "other",
    ports: int | None = None,
    server: str | None = None,
    community: str | None = None,
    description: str | None = None,
    is_active: bool = True,
) -> NasDevice:
    """Create the inventory row and the FreeRADIUS nas row in one transaction."""
    device = NasDevice(
        name=name,
        ip_address=ip_address,
        shortname=shortname,
        nas_type=nas_type,
        secret_encrypted=encrypt_secret(secret),
        ports=ports,
        server=server,
        community=community,
        description=description,
        is_active=is_active,
    )
    session.add(device)
    # no_autoflush: the nas sync SELECT would otherwise flush the pending
    # INSERT early, letting a duplicate-name IntegrityError escape the
    # _commit_or_conflict mapping below.
    with session.no_autoflush:
        if is_active:
            await _sync_nas_row(session, device, secret)
    await _commit_or_conflict(session, "NAS device name or IP address already exists")
    await audit_service.record_audit(
        session,
        admin_id=actor_id,
        action="create",
        resource="nas_devices",
        resource_id=str(device.id),
        metadata_={"name": name, "ip_address": ip_address},
    )
    return device


async def update_nas_device(
    session: AsyncSession,
    device: NasDevice,
    *,
    actor_id: int,
    name: str | None = None,
    shortname: str | None = None,
    nas_type: str | None = None,
    secret: str | None = None,
    ports: int | None = None,
    server: str | None = None,
    community: str | None = None,
    description: str | None = None,
    is_active: bool | None = None,
) -> NasDevice:
    """Apply inventory changes; secret/fields/is_active re-sync the nas row."""
    changed: list[str] = []
    plaintext: str | None = None
    if name is not None and name != device.name:
        device.name = name
        changed.append("name")
    if shortname is not None and shortname != device.shortname:
        device.shortname = shortname
        changed.append("shortname")
    if nas_type is not None and nas_type != device.nas_type:
        device.nas_type = nas_type
        changed.append("nas_type")
    if secret is not None:
        device.secret_encrypted = encrypt_secret(secret)
        plaintext = secret
        changed.append("secret")
    if ports is not None and ports != device.ports:
        device.ports = ports
        changed.append("ports")
    if server is not None and server != device.server:
        device.server = server
        changed.append("server")
    if community is not None and community != device.community:
        device.community = community
        changed.append("community")
    if description is not None and description != device.description:
        device.description = description
        changed.append("description")
    if is_active is not None and is_active != device.is_active:
        device.is_active = is_active
        changed.append("is_active")

    if changed:
        with session.no_autoflush:
            if device.is_active:
                # a rotated secret takes precedence; otherwise decrypt the stored one
                await _sync_nas_row(
                    session, device, plaintext or decrypt_secret(device.secret_encrypted)
                )
            else:
                await _remove_nas_row(session, device.ip_address)
        await _commit_or_conflict(session, "NAS device name or IP address already exists")
        await audit_service.record_audit(
            session,
            admin_id=actor_id,
            action="update",
            resource="nas_devices",
            resource_id=str(device.id),
            metadata_={"name": device.name, "fields": changed},
        )
    return device


async def delete_nas_device(session: AsyncSession, device: NasDevice, actor_id: int) -> None:
    """Delete the inventory row and the FreeRADIUS nas row in one transaction."""
    ip_address = device.ip_address
    device_id = device.id
    with session.no_autoflush:
        await _remove_nas_row(session, ip_address)
        await session.delete(device)
    await session.commit()
    await audit_service.record_audit(
        session,
        admin_id=actor_id,
        action="delete",
        resource="nas_devices",
        resource_id=str(device_id),
        metadata_={"name": device.name, "ip_address": ip_address},
    )

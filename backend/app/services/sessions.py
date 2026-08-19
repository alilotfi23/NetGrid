"""Live-session service: read-only radacct queries (Phase 9, read side).

Sessions are pure reads against FreeRADIUS's radacct table — nothing here
ever writes to it. An "open" session is a row with acctstoptime IS NULL; the
CoA/disconnect write path lives in app.services.disconnect. The FreeRADIUS
`nas` table is joined (on nasname = nasipaddress) to resolve each session's
NAS IP to its human-friendly shortname, and `subscribers` (on username) to
resolve the subscriber profile id, both for the dashboard.
"""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.radius import Nas, RadAcct
from app.models.subscriber import Subscriber


def _session_to_dict(
    row: RadAcct, nas_shortname: str | None = None, subscriber_id: int | None = None
) -> dict[str, object]:
    """Serialize one radacct row, casting inet columns to str for JSON."""
    return {
        "id": row.id,
        "username": row.username,
        "nasipaddress": str(row.nasipaddress) if row.nasipaddress else None,
        "nas_shortname": nas_shortname,
        "subscriber_id": subscriber_id,
        "acctstarttime": row.acctstarttime,
        "acctsessiontime": row.acctsessiontime,
        "acctinputoctets": row.acctinputoctets,
        "acctoutputoctets": row.acctoutputoctets,
        "framedipaddress": str(row.framedipaddress) if row.framedipaddress else None,
    }


# nasname is text while nasipaddress is inet. `inet::text` would include
# the netmask suffix (192.168.0.10/32) and text-vs-inet has no implicit
# cast, so both sides meet on host(nasipaddress) — the bare IP string,
# which is exactly what our nas-table sync stores as nasname.
_NAS_MATCH = func.host(RadAcct.nasipaddress) == Nas.nasname


async def list_live_sessions(
    session: AsyncSession, page: int, page_size: int, q: str | None = None
) -> tuple[list[dict[str, object]], int]:
    """Paginated open sessions (acctstoptime IS NULL), newest start first.

    Left-joins the nas and subscribers tables so each session carries its
    NAS shortname and subscriber profile id when they exist. `q` matches
    username, NAS shortname, or NAS IP (case-insensitive).
    """
    base = (
        select(RadAcct, Nas.shortname, Subscriber.id)
        .outerjoin(Nas, _NAS_MATCH)
        .outerjoin(Subscriber, Subscriber.username == RadAcct.username)
        .where(RadAcct.acctstoptime.is_(None))
    )
    count_stmt = select(func.count()).select_from(base.subquery())
    stmt = base.order_by(RadAcct.acctstarttime.desc())
    if q:
        like = f"%{q}%"
        clause = or_(
            RadAcct.username.ilike(like),
            func.host(RadAcct.nasipaddress).ilike(like),
            Nas.shortname.ilike(like),
        )
        count_stmt = select(func.count()).select_from(base.where(clause).subquery())
        stmt = stmt.where(clause)
    total = (await session.execute(count_stmt)).scalar_one()
    result = await session.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    return [
        _session_to_dict(row, shortname, subscriber_id)
        for row, shortname, subscriber_id in result.all()
    ], int(total)


async def get_live_session_stats(
    session: AsyncSession,
) -> tuple[int, list[tuple[str, int, str | None]]]:
    """Open-session counts: (total, by_nas) for the dashboard card.

    by_nas is [(nasipaddress, count, nas_shortname)] sorted by count
    descending, then IP, so the busiest NAS leads the card; shortname is
    None when the NAS IP has no nas-table row.
    """
    total = (
        await session.execute(
            select(func.count()).select_from(RadAcct).where(RadAcct.acctstoptime.is_(None))
        )
    ).scalar_one()
    rows = await session.execute(
        select(RadAcct.nasipaddress, func.count(), Nas.shortname)
        .outerjoin(Nas, _NAS_MATCH)
        .where(RadAcct.acctstoptime.is_(None))
        .group_by(RadAcct.nasipaddress, Nas.shortname)
        .order_by(func.count().desc(), RadAcct.nasipaddress)
    )
    by_nas = [(str(nas), int(count), shortname) for nas, count, shortname in rows.all()]
    return int(total), by_nas

"""Live-session service: read-only radacct queries (Phase 9, read side).

Sessions are pure reads against FreeRADIUS's radacct table — nothing here
ever writes to it. An "open" session is a row with acctstoptime IS NULL; the
CoA/disconnect write path arrives with the rest of Phase 9.
"""

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.radius import RadAcct


def _session_to_dict(row: RadAcct) -> dict[str, object]:
    """Serialize one radacct row, casting inet columns to str for JSON."""
    return {
        "id": row.id,
        "username": row.username,
        "nasipaddress": str(row.nasipaddress) if row.nasipaddress else None,
        "acctstarttime": row.acctstarttime,
        "acctsessiontime": row.acctsessiontime,
        "acctinputoctets": row.acctinputoctets,
        "acctoutputoctets": row.acctoutputoctets,
        "framedipaddress": str(row.framedipaddress) if row.framedipaddress else None,
    }


async def list_live_sessions(
    session: AsyncSession, page: int, page_size: int, q: str | None = None
) -> tuple[list[dict[str, object]], int]:
    """Paginated open sessions (acctstoptime IS NULL), newest start first.

    `q` matches username (case-insensitive) or NAS IP (as text).
    """
    base = select(RadAcct).where(RadAcct.acctstoptime.is_(None))
    count_stmt = select(func.count()).select_from(base.subquery())
    stmt = base.order_by(RadAcct.acctstarttime.desc())
    if q:
        like = f"%{q}%"
        clause = or_(RadAcct.username.ilike(like), cast(RadAcct.nasipaddress, String).ilike(like))
        count_stmt = select(func.count()).select_from(base.where(clause).subquery())
        stmt = stmt.where(clause)
    total = (await session.execute(count_stmt)).scalar_one()
    result = await session.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    return [_session_to_dict(row) for row in result.scalars().all()], int(total)


async def get_live_session_stats(session: AsyncSession) -> tuple[int, list[tuple[str, int]]]:
    """Open-session counts: (total, by_nas) for the dashboard card.

    by_nas is [(nasipaddress, count)] sorted by count descending, then IP, so
    the busiest NAS leads the card.
    """
    total = (
        await session.execute(
            select(func.count()).select_from(RadAcct).where(RadAcct.acctstoptime.is_(None))
        )
    ).scalar_one()
    rows = await session.execute(
        select(RadAcct.nasipaddress, func.count())
        .where(RadAcct.acctstoptime.is_(None))
        .group_by(RadAcct.nasipaddress)
        .order_by(func.count().desc(), RadAcct.nasipaddress)
    )
    by_nas = [(str(nas), int(count)) for nas, count in rows.all()]
    return int(total), by_nas

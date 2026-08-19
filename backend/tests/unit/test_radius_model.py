"""Unit tests for the RadCheck model (exact FreeRADIUS radcheck mapping)."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.radius import RadCheck


async def test_radcheck_defaults(session):
    row = RadCheck(username="u1", attribute="Cleartext-Password", value="pw")
    session.add(row)
    await session.commit()
    assert row.id is not None
    assert row.op == "=="  # FreeRADIUS default from schema.sql


async def test_radcheck_unique_username_attribute(session):
    session.add(RadCheck(username="u1", attribute="Cleartext-Password", op=":=", value="a"))
    await session.commit()
    session.add(RadCheck(username="u1", attribute="Cleartext-Password", op=":=", value="b"))
    with pytest.raises(IntegrityError):
        await session.commit()

"""Unit tests for the RadCheck model (exact FreeRADIUS radcheck mapping)."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.radius import RadCheck


async def test_radcheck_defaults(session):
    row = RadCheck(UserName="u1", Attribute="Cleartext-Password", Value="pw")
    session.add(row)
    await session.commit()
    assert row.id is not None
    assert row.op == "=="  # FreeRADIUS default from schema.sql


async def test_radcheck_unique_username_attribute(session):
    session.add(RadCheck(UserName="u1", Attribute="Cleartext-Password", op=":=", Value="a"))
    await session.commit()
    session.add(RadCheck(UserName="u1", Attribute="Cleartext-Password", op=":=", Value="b"))
    with pytest.raises(IntegrityError):
        await session.commit()

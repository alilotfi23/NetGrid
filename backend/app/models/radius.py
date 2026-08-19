"""Read-write SQLAlchemy mappings of FreeRADIUS's rad* tables.

Column names follow the *effective* schema created by
freeradius/raddb/mods-config/sql/main/postgresql/schema.sql: that file
declares mixed-case names (UserName, Attribute, Value) but unquoted, and
PostgreSQL folds unquoted identifiers to lowercase — so the real tables
(and the columns FreeRADIUS's authorize/group queries select) are
lowercase. Do not rename (CLAUDE.md). The app writes subscriber
credentials here (direct coupling); the tables are created by the
FreeRADIUS initdb in dev/prod and by Base.metadata.create_all in tests.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class RadCheck(Base):
    __tablename__ = "radcheck"
    __table_args__ = (
        UniqueConstraint("username", "attribute", name="uq_radcheck_username_attribute"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(Text, nullable=False, default="")
    attribute: Mapped[str] = mapped_column(Text, nullable=False, default="")
    op: Mapped[str] = mapped_column(String(2), nullable=False, default="==")
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")


class RadGroupCheck(Base):
    """radgroupcheck — group-level auth checks (op defaults to `==`)."""

    __tablename__ = "radgroupcheck"

    id: Mapped[int] = mapped_column(primary_key=True)
    groupname: Mapped[str] = mapped_column(Text, nullable=False, default="")
    attribute: Mapped[str] = mapped_column(Text, nullable=False, default="")
    op: Mapped[str] = mapped_column(String(2), nullable=False, default="==")
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")


class RadGroupReply(Base):
    """radgroupreply — attributes returned on Access-Accept (op defaults to `=`)."""

    __tablename__ = "radgroupreply"

    id: Mapped[int] = mapped_column(primary_key=True)
    groupname: Mapped[str] = mapped_column(Text, nullable=False, default="")
    attribute: Mapped[str] = mapped_column(Text, nullable=False, default="")
    op: Mapped[str] = mapped_column(String(2), nullable=False, default="=")
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")


class RadUserGroup(Base):
    """radusergroup — subscriber-to-group membership (priority orders groups)."""

    __tablename__ = "radusergroup"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(Text, nullable=False, default="")
    groupname: Mapped[str] = mapped_column(Text, nullable=False, default="")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Nas(Base):
    """FreeRADIUS's nas table — the devices allowed to authenticate.

    One row per NetGrid NasDevice, synced in the same transaction: nasname is
    the device's ip_address, and secret is the *plaintext* shared secret
    (FreeRADIUS must recover it for PAP/CHAP; the encrypted copy lives in
    nas_devices.secret_encrypted). An inactive device has no row here, so
    FreeRADIUS treats it as an unknown NAS and rejects it.
    """

    __tablename__ = "nas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nasname: Mapped[str] = mapped_column(Text, nullable=False)
    shortname: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False, default="other")
    ports: Mapped[int | None] = mapped_column(Integer)
    secret: Mapped[str] = mapped_column(Text, nullable=False)
    server: Mapped[str | None] = mapped_column(Text)
    community: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)


class RadAcct(Base):
    """Read-only mapping of FreeRADIUS's radacct table (session accounting).

    Only the columns the dashboard's live-session views need are mapped;
    writes are never performed against this table. Inet columns surface as
    ipaddress objects — cast to str at the service layer.
    """

    __tablename__ = "radacct"

    id: Mapped[int] = mapped_column("radacctid", BigInteger, primary_key=True)
    acctsessionid: Mapped[str | None] = mapped_column(Text)
    username: Mapped[str | None] = mapped_column(Text)
    nasipaddress: Mapped[str | None] = mapped_column(INET)
    acctstarttime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acctstoptime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acctsessiontime: Mapped[int | None] = mapped_column(BigInteger)
    acctinputoctets: Mapped[int | None] = mapped_column(BigInteger)
    acctoutputoctets: Mapped[int | None] = mapped_column(BigInteger)
    framedipaddress: Mapped[str | None] = mapped_column(INET)

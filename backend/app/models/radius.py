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

from sqlalchemy import Integer, String, Text, UniqueConstraint
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

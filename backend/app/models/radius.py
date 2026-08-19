"""Read-write SQLAlchemy mapping of FreeRADIUS's radcheck table.

Column names follow the *effective* schema created by
freeradius/raddb/mods-config/sql/main/postgresql/schema.sql: that file
declares mixed-case names (UserName, Attribute, Value) but unquoted, and
PostgreSQL folds unquoted identifiers to lowercase — so the real table
(and the columns FreeRADIUS's authorize query selects) is
`id, username, attribute, op, value`. Do not rename (CLAUDE.md). The app
writes subscriber credentials here (direct coupling); the table itself is
created by the FreeRADIUS initdb in dev/prod and by
Base.metadata.create_all in tests. The UniqueConstraint mirrors the
hardened index uq_radcheck_username_attribute (indexes.sql).
"""

from sqlalchemy import String, Text, UniqueConstraint
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

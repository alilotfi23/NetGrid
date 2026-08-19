from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class NasDevice(TimestampMixin, Base):
    """NetGrid's NAS inventory (source of truth).

    The shared secret is stored Fernet-encrypted at rest (secret_encrypted).
    The FreeRADIUS `nas` table holds the plaintext secret FreeRADIUS needs to
    authenticate the device — the same direct-coupling idiom as radcheck's
    Cleartext-Password (CLAUDE.md). ip_address is the RADIUS identity
    (nas.nasname) and is immutable after creation.
    """

    __tablename__ = "nas_devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), unique=True, nullable=False)
    shortname: Mapped[str] = mapped_column(String(64), nullable=False)
    nas_type: Mapped[str] = mapped_column(String(32), default="other", nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(String(512), nullable=False)
    ports: Mapped[int | None] = mapped_column(Integer)
    server: Mapped[str | None] = mapped_column(String(64))
    community: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

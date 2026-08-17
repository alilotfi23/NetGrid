from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class NasDevice(TimestampMixin, Base):
    __tablename__ = "nas_devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), unique=True, nullable=False)
    shortname: Mapped[str] = mapped_column(String(64), nullable=False)
    nas_type: Mapped[str] = mapped_column(String(32), default="other", nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

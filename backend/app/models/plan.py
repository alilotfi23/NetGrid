from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .subscriber import Subscriber


class Plan(TimestampMixin, Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    radius_group: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    bandwidth_down_mbps: Mapped[int] = mapped_column(Integer, nullable=False)
    bandwidth_up_mbps: Mapped[int] = mapped_column(Integer, nullable=False)
    quota_gb: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Opt-in switch for the over-quota enforcement job: when true, the
    # subscriber is disconnected (CoA) once current-month usage hits quota_gb.
    enforce_quota: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    subscribers: Mapped[list["Subscriber"]] = relationship(back_populates="plan")

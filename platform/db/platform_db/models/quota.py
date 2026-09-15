"""Persistence model for a licensed source's daily call budget.

A licence's daily budget must survive process restarts and be shared by every
worker, so counting calls in memory is not an option: it resets on every run
and cannot see what another worker already spent. One row per source per day,
updated atomically, is the only way the count outlives the process that made
the call.
"""

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Integer, PrimaryKeyConstraint, String, func
from sqlalchemy.orm import Mapped, mapped_column

from platform_db.base import Base
from platform_db.models.ingestion import SOURCE_KEY_LENGTH


class SourceQuotaUsage(Base):
    """Calls made by one source on one UTC day."""

    __tablename__ = "source_quota_usage"
    __table_args__ = (
        PrimaryKeyConstraint("source_key", "day", name="pk_source_quota_usage"),
        CheckConstraint("calls >= 0", name="ck_source_quota_usage_calls_not_negative"),
    )

    source_key: Mapped[str] = mapped_column(String(SOURCE_KEY_LENGTH), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

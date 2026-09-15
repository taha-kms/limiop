"""Reserving a licensed source's daily call budget, atomically.

A read of how many calls a source has made today, followed by a write of one
more, is not atomic across two workers, or across two runs of the same
source: both can read the same count, both decide there is room, and both
write, and the budget is exceeded by however many raced. The check and the
increment have to happen in one statement so a write that would push the
total over the budget never lands, no matter how many sessions ask at once.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime

from platform_db.models import SourceQuotaUsage
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

# `quota` names the table so the DO UPDATE and RETURNING clauses can refer to
# the row already on disk, not the values this statement is trying to insert.
_RESERVE_SQL = text(
    """
    INSERT INTO source_quota_usage AS quota (source_key, day, calls)
    SELECT :source_key, :day, :calls
    WHERE :calls <= :per_day
    ON CONFLICT (source_key, day) DO UPDATE
    SET calls = quota.calls + EXCLUDED.calls,
        updated_at = now()
    WHERE quota.calls + EXCLUDED.calls <= :per_day
    RETURNING quota.calls
    """
)


@dataclass(frozen=True, slots=True)
class Quota:
    """A source's daily call budget."""

    per_day: int

    def __post_init__(self) -> None:
        if self.per_day < 1:
            raise ValueError("per_day must be at least 1")


def _today(today: date | None) -> date:
    return today if today is not None else datetime.now(UTC).date()


async def reserve(
    session: AsyncSession,
    source_key: str,
    *,
    calls: int = 1,
    quota: Quota,
    today: date | None = None,
) -> bool:
    """Reserve `calls` more calls for `source_key` on `today`, or refuse.

    Whether the row already exists is not this caller's concern: a fresh
    source starting its first call today and a source already partway through
    its budget are gated by the same `WHERE`, so a first reservation for more
    than the budget allows is refused exactly like a later one would be,
    rather than writing a row that is already over budget.

    Returns True and stores the increment when today's total, including this
    reservation, fits the budget. Returns False and writes nothing otherwise.
    """
    result = await session.execute(
        _RESERVE_SQL,
        {
            "source_key": source_key,
            "day": _today(today),
            "calls": calls,
            "per_day": quota.per_day,
        },
    )
    return result.scalar_one_or_none() is not None


async def used_today(
    session: AsyncSession,
    source_key: str,
    today: date | None = None,
) -> int:
    """How many calls `source_key` has already made on `today`."""
    result = await session.execute(
        select(SourceQuotaUsage.calls).where(
            SourceQuotaUsage.source_key == source_key,
            SourceQuotaUsage.day == _today(today),
        )
    )
    return result.scalar_one_or_none() or 0

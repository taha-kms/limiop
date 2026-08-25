"""PostgreSQL persistence operations for the job catalog."""

from datetime import datetime
from uuid import UUID

from platform_db.models import JobProvenance
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession


async def observe_job_provenance(
    session: AsyncSession,
    *,
    job_id: UUID,
    source_id: UUID,
    source_job_id: str,
    source_url: str,
    seen_at: datetime,
    raw_payload: dict[str, object] | None = None,
) -> JobProvenance:
    """Insert or refresh one external record without owning the transaction."""
    if seen_at.tzinfo is None or seen_at.utcoffset() is None:
        raise ValueError("seen_at must be timezone-aware")

    insert_statement = insert(JobProvenance).values(
        job_id=job_id,
        source_id=source_id,
        source_job_id=source_job_id,
        source_url=source_url,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        raw_payload=raw_payload,
    )
    excluded = insert_statement.excluded
    statement = insert_statement.on_conflict_do_update(
        constraint="uq_job_provenance_source_id_source_job_id",
        set_={
            "source_url": excluded.source_url,
            "first_seen_at": func.least(
                JobProvenance.first_seen_at,
                excluded.first_seen_at,
            ),
            "last_seen_at": func.greatest(
                JobProvenance.last_seen_at,
                excluded.last_seen_at,
            ),
            "raw_payload": func.coalesce(
                excluded.raw_payload,
                JobProvenance.raw_payload,
            ),
            # Seeing it again undoes the conclusion that it was gone. A posting
            # that comes back is the posting it was, not a new one, so this is
            # cleared here rather than by anything that has to remember to.
            "retired_at": None,
        },
    ).returning(JobProvenance)

    return (await session.scalars(statement)).one()

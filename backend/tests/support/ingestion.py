"""Ingestion-run fixtures for tests that need a run history.

Written here rather than in the catalog helper because a run is not a posting:
a source can have run without creating anything, and a posting can outlive
every run that touched it.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from platform_db.models.ingestion import IngestionRun, IngestionRunState
from sqlalchemy import delete

from app.db.session import Database

EPOCH = datetime(2026, 8, 1, 12, tzinfo=UTC)


def ran(hours: int) -> datetime:
    """A run time, offset from a fixed point so tests never use the clock."""
    return EPOCH + timedelta(hours=hours)


async def clear_runs(database: Database) -> None:
    async with database.session() as session:
        await session.execute(delete(IngestionRun))
        await session.commit()


async def seed_runs(database: Database, *specs: dict[str, Any]) -> None:
    """Insert one run per spec, defaulting to a clean completed run."""
    async with database.session() as session:
        for spec in specs:
            state = spec.get("state", IngestionRunState.COMPLETED)
            started_at = spec.get("started_at", EPOCH)
            session.add(
                IngestionRun(
                    source_key=str(spec["source_key"]),
                    state=state,
                    started_at=started_at,
                    finished_at=(
                        None
                        if state is IngestionRunState.RUNNING
                        else spec.get("finished_at", started_at + timedelta(minutes=2))
                    ),
                    fetched=spec.get("fetched", 0),
                    created=spec.get("created", 0),
                    updated=spec.get("updated", 0),
                    skipped=spec.get("skipped", 0),
                    failed=spec.get("failed", 0),
                )
            )
        await session.commit()


async def with_empty_runs(
    database: Database,
    test: Callable[[Database], Awaitable[None]],
) -> None:
    """Run one test against a history that starts and ends empty."""
    try:
        await clear_runs(database)
        await test(database)
    finally:
        await clear_runs(database)

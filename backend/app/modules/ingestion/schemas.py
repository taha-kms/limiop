"""What an ingestion run looks like to somebody checking on it."""

from datetime import datetime
from typing import Any

from platform_db.models.ingestion import IngestionRunState
from pydantic import BaseModel, ConfigDict


class IngestionRunReport(BaseModel):
    """One source's most recent run.

    Facts rather than a verdict. What counts as too old depends on a schedule
    this does not know, so it reports when the run finished and leaves the
    judgement to whoever set the schedule.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_key: str
    state: IngestionRunState
    started_at: datetime
    # Null while the run is in flight, which the state also says.
    finished_at: datetime | None
    fetched: int
    created: int
    updated: int
    skipped: int
    failed: int

    @classmethod
    def of(cls, run: Any) -> "IngestionRunReport":
        return cls(
            source_key=run.source_key,
            state=run.state,
            started_at=run.started_at,
            finished_at=run.finished_at,
            fetched=run.fetched,
            created=run.created,
            updated=run.updated,
            skipped=run.skipped,
            failed=run.failed,
        )


class IngestionStatusResponse(BaseModel):
    """The most recent run of every source that has ever run.

    A source that has never run is absent rather than listed as idle, so a
    pipeline that was never deployed cannot read as a healthy one.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    runs: list[IngestionRunReport]

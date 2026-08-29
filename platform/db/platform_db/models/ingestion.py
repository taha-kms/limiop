"""Persistence model for one execution of an ingestion pipeline.

A run outlives the task that produced it. Scheduler logs are ephemeral and are
the wrong place to answer "did last night's Greenhouse run finish", so the
answer is a row.

The row's own identifier is the correlation identifier for the run: everything
this execution wrote can be tied back to it, and nothing else needs generating.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from platform_db.base import Base
from platform_db.models.skills import VOCABULARY_VERSION_LENGTH

SOURCE_KEY_LENGTH = 64


class IngestionRunState(StrEnum):
    """Where a run got to.

    A run is `RUNNING` only while it is. Both other states are terminal, and one
    of them is always reached: a run that ends without saying which is a run
    that crashed hard enough to lose the process, which is itself worth seeing.
    """

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class IngestionRun(Base):
    """One execution of one provider's pipeline, and what it did."""

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint(
            "state IN ('running', 'completed', 'failed')",
            name="ck_ingestion_runs_state",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_ingestion_runs_timestamp_order",
        ),
        CheckConstraint(
            "(state = 'running') = (finished_at IS NULL)",
            name="ck_ingestion_runs_finished_when_terminal",
        ),
        Index("ix_ingestion_runs_source_key_started_at", "source_key", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_key: Mapped[str] = mapped_column(String(SOURCE_KEY_LENGTH), nullable=False)
    state: Mapped[IngestionRunState] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Whether this run was entitled to conclude a posting is gone. Stored
    # because the conclusion is drawn from it and a reader auditing a
    # withdrawal needs to see what licensed it.
    reached_the_end: Mapped[bool] = mapped_column(nullable=False, default=False)
    stopped_at_budget: Mapped[bool] = mapped_column(nullable=False, default=False)

    alias_version: Mapped[str | None] = mapped_column(
        String(VOCABULARY_VERSION_LENGTH), nullable=True
    )
    mentions_resolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mentions_unknown: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extraction_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Counts per stage and a bounded sample of reasons. Never a traceback and
    # never a provider payload: a diagnostic that has to be redacted before it
    # can be read is one nobody reads.
    failure_summary: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )

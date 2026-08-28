"""Wiring and entry point for a Greenhouse ingestion run.

Everything reusable lives in `ingestion.pipeline`. This module names the
concrete parts, owns their lifecycles, and folds in the boards that could not
be read, which the generic run has no way to learn about.
"""

from dataclasses import replace
from datetime import UTC, datetime

import httpx2

from job_ingestion.config import Settings, get_settings
from job_ingestion.contracts import IngestionSummary
from job_ingestion.database import Database
from job_ingestion.greenhouse.client import (
    DEFAULT_BASE_URL,
    SOURCE_KEY,
    GreenhouseClient,
    GreenhouseConfig,
)
from job_ingestion.greenhouse.normalizer import GreenhouseNormalizer
from job_ingestion.greenhouse.records import GreenhouseJobRecord, GreenhouseValidator
from job_ingestion.persistence import SourceRegistration
from job_ingestion.pipeline import DEFAULT_MAX_RECORDS, IngestionRun
from job_ingestion.reconciliation import ReconciliationResult, reconcile

DISPLAY_NAME = "Greenhouse"

# Above the aggregator. An employer's own board is the better account of its own
# posting, which is what source precedence exists to express.
PRECEDENCE = 20

# Boards are listed rather than discovered. A guessed board name that resolves
# to a different company would ingest its postings under the wrong employer, so
# adding one is a deliberate act until #120 makes it a safe one.
DEFAULT_BOARDS = (
    "anthropic",
    "datadog",
    "hudl",
)


def build_run(
    client: GreenhouseClient,
    max_records: int,
    *,
    skill_alias_version: str | None = None,
) -> IngestionRun[GreenhouseJobRecord]:
    """Assemble the stages around an already-built client."""
    return IngestionRun(
        client=client,
        validator=GreenhouseValidator(),
        normalizer=GreenhouseNormalizer(),
        source=SourceRegistration(
            key=SOURCE_KEY,
            display_name=DISPLAY_NAME,
            base_url=client.config.base_url,
            precedence=PRECEDENCE,
        ),
        max_records=max_records,
        skill_alias_version=skill_alias_version,
    )


def default_config() -> GreenhouseConfig:
    return GreenhouseConfig(boards=DEFAULT_BOARDS, base_url=DEFAULT_BASE_URL)


def with_board_failures(summary: IngestionSummary, client: GreenhouseClient) -> IngestionSummary:
    """Add the boards that could not be read to what the run reports.

    The generic run only sees the pages it was handed, so a board skipped by the
    client would otherwise vanish from the summary and the run would look
    complete while a company was missing entirely.
    """
    if not client.failures:
        return summary
    return replace(summary, failures=summary.failures + tuple(client.failures))


async def ingest_greenhouse(
    *,
    config: GreenhouseConfig | None = None,
    max_records: int = DEFAULT_MAX_RECORDS,
    settings: Settings | None = None,
    http_client: httpx2.AsyncClient | None = None,
) -> IngestionSummary:
    """Run one complete Greenhouse ingestion against the configured database."""
    app_settings = settings if settings is not None else get_settings()
    database = Database(app_settings.database_url)
    resolved = config if config is not None else default_config()
    started_at = datetime.now(UTC)
    try:
        async with GreenhouseClient(resolved, http_client=http_client) as client:
            summary = with_board_failures(
                await build_run(
                    client,
                    max_records,
                    skill_alias_version=app_settings.skill_alias_version,
                ).execute(database),
                client,
            )
        await reconcile_after(database, summary, run_started_at=started_at)
        return summary
    finally:
        await database.dispose()


async def reconcile_after(
    database: Database,
    summary: IngestionSummary,
    *,
    run_started_at: datetime,
) -> ReconciliationResult:
    """Conclude what this run is entitled to conclude, if anything.

    Run against the assembled summary rather than inside the run, so a failure
    recorded after the last page still denies the conclusion.
    """
    async with database.session() as session:
        result = await reconcile(session, summary, run_started_at=run_started_at)
        await session.commit()
    return result

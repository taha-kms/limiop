"""Wiring and entry point for the Arbeitnow ingestion run.

Everything reusable lives in `ingestion.pipeline`. This module only names the
concrete parts and owns their lifecycles, so a scheduler can start a run without
knowing any stage.
"""

from datetime import UTC, datetime

import httpx2

from job_ingestion.arbeitnow.client import (
    SOURCE_KEY,
    ArbeitnowClient,
    ArbeitnowConfig,
)
from job_ingestion.arbeitnow.normalizer import ArbeitnowNormalizer
from job_ingestion.arbeitnow.records import ArbeitnowJobRecord, ArbeitnowValidator
from job_ingestion.config import Settings, get_settings
from job_ingestion.contracts import IngestionSummary
from job_ingestion.database import Database
from job_ingestion.persistence import SourceRegistration
from job_ingestion.pipeline import DEFAULT_MAX_RECORDS, IngestionRun
from job_ingestion.reconciliation import ReconciliationResult, reconcile

DISPLAY_NAME = "Arbeitnow"

# Arbeitnow aggregates postings that employers publish on their own boards,
# so where the two disagree the board is the better account. Ranked below
# them, and above nothing, since it is the only source until one is added.
PRECEDENCE = 10


def build_run(
    client: ArbeitnowClient,
    max_records: int,
    *,
    skill_alias_version: str | None = None,
) -> IngestionRun[ArbeitnowJobRecord]:
    """Assemble the stages around an already-built client."""
    return IngestionRun(
        client=client,
        validator=ArbeitnowValidator(),
        normalizer=ArbeitnowNormalizer(),
        source=SourceRegistration(
            key=SOURCE_KEY,
            display_name=DISPLAY_NAME,
            base_url=client.config.base_url,
            precedence=PRECEDENCE,
        ),
        max_records=max_records,
        skill_alias_version=skill_alias_version,
    )


def arbeitnow_run(
    config: ArbeitnowConfig | None = None,
    *,
    http_client: httpx2.AsyncClient | None = None,
    max_records: int = DEFAULT_MAX_RECORDS,
    skill_alias_version: str | None = None,
) -> IngestionRun[ArbeitnowJobRecord]:
    """Build a bounded Arbeitnow ingestion run around a caller-managed client."""
    settings = config if config is not None else ArbeitnowConfig()
    return build_run(
        ArbeitnowClient(settings, http_client=http_client),
        max_records,
        skill_alias_version=skill_alias_version,
    )


async def ingest_arbeitnow(
    *,
    config: ArbeitnowConfig | None = None,
    max_records: int = DEFAULT_MAX_RECORDS,
    settings: Settings | None = None,
    http_client: httpx2.AsyncClient | None = None,
) -> IngestionSummary:
    """Run one complete Arbeitnow ingestion against the configured database.

    This is the entry point a scheduler calls. It owns the database engine, and
    the HTTP client unless one is supplied, and closes what it owns whatever the
    run reports.
    """
    app_settings = settings if settings is not None else get_settings()
    database = Database(app_settings.database_url)
    resolved = config if config is not None else ArbeitnowConfig()
    started_at = datetime.now(UTC)
    try:
        async with ArbeitnowClient(resolved, http_client=http_client) as client:
            summary = await build_run(
                client,
                max_records,
                skill_alias_version=app_settings.skill_alias_version,
            ).execute(database)
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

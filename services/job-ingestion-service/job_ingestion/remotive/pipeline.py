"""Wiring and entry point for the Remotive ingestion run.

Everything reusable lives in `ingestion.pipeline`. This module only names the
concrete parts and owns their lifecycles, so a scheduler can start a run without
knowing any stage.
"""

from datetime import UTC, datetime

import httpx2

from job_ingestion.config import Settings, get_settings
from job_ingestion.contracts import IngestionSummary
from job_ingestion.database import Database
from job_ingestion.persistence import SourceRegistration
from job_ingestion.pipeline import DEFAULT_MAX_RECORDS, IngestionRun
from job_ingestion.remotive.client import (
    SOURCE_KEY,
    RemotiveClient,
    RemotiveConfig,
)
from job_ingestion.remotive.normalizer import RemotiveNormalizer
from job_ingestion.remotive.records import RemotiveJobRecord, RemotiveValidator
from job_ingestion.runs import run_recorded_ingestion

DISPLAY_NAME = "Remotive"

# Remotive aggregates postings employers publish elsewhere, so where the two
# disagree the original is the better account. Ranked below employer boards,
# and above nothing else until a second aggregator is added.
PRECEDENCE = 10


def build_run(
    client: RemotiveClient,
    max_records: int,
    *,
    skill_alias_version: str | None = None,
) -> IngestionRun[RemotiveJobRecord]:
    """Assemble the stages around an already-built client."""
    return IngestionRun(
        client=client,
        validator=RemotiveValidator(),
        normalizer=RemotiveNormalizer(),
        source=SourceRegistration(
            key=SOURCE_KEY,
            display_name=DISPLAY_NAME,
            base_url=client.config.base_url,
            precedence=PRECEDENCE,
        ),
        max_records=max_records,
        skill_alias_version=skill_alias_version,
    )


def remotive_run(
    config: RemotiveConfig | None = None,
    *,
    http_client: httpx2.AsyncClient | None = None,
    max_records: int = DEFAULT_MAX_RECORDS,
    skill_alias_version: str | None = None,
) -> IngestionRun[RemotiveJobRecord]:
    """Build a bounded Remotive ingestion run around a caller-managed client."""
    settings = config if config is not None else RemotiveConfig()
    return build_run(
        RemotiveClient(settings, http_client=http_client),
        max_records,
        skill_alias_version=skill_alias_version,
    )


async def ingest_remotive(
    *,
    config: RemotiveConfig | None = None,
    max_records: int = DEFAULT_MAX_RECORDS,
    settings: Settings | None = None,
    http_client: httpx2.AsyncClient | None = None,
) -> IngestionSummary:
    """Run one complete Remotive ingestion against the configured database.

    This is the entry point a scheduler calls. It owns the database engine, and
    the HTTP client unless one is supplied, and closes what it owns whatever the
    run reports. The record/reconcile/complete sequence around the run itself
    lives in `run_recorded_ingestion`, shared with every other provider's
    entry point.
    """
    app_settings = settings if settings is not None else get_settings()
    database = Database(app_settings.database_url)
    resolved = config if config is not None else RemotiveConfig()
    started_at = datetime.now(UTC)

    async def build(database: Database) -> IngestionSummary:
        async with RemotiveClient(resolved, http_client=http_client) as client:
            return await build_run(
                client,
                max_records,
                skill_alias_version=app_settings.skill_alias_version,
            ).execute(database)

    try:
        return await run_recorded_ingestion(database, SOURCE_KEY, build, started_at=started_at)
    finally:
        await database.dispose()

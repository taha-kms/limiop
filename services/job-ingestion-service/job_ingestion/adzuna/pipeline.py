"""Wiring and entry point for the Adzuna ingestion run.

Everything reusable lives in `ingestion.pipeline`. This module only names the
concrete parts and owns their lifecycles, so a scheduler can start a run without
knowing any stage.

Adzuna is the first keyed source, so the entry point opens by asking for its
credentials. A deployment that has not set them gets a recorded run saying so
and nothing is fetched; that is an ordinary state, not a failure of the task.
"""

from datetime import UTC, datetime

import httpx2

from job_ingestion.adzuna.client import AdzunaClient, AdzunaConfig
from job_ingestion.adzuna.normalizer import AdzunaNormalizer
from job_ingestion.adzuna.records import AdzunaJobRecord, AdzunaValidator
from job_ingestion.adzuna.source import CREDENTIALS, DISPLAY_NAME, PRECEDENCE, SOURCE_KEY
from job_ingestion.config import Settings, get_settings
from job_ingestion.contracts import IngestionSummary
from job_ingestion.credentials import require
from job_ingestion.database import Database
from job_ingestion.persistence import SourceRegistration
from job_ingestion.pipeline import DEFAULT_MAX_RECORDS, IngestionRun
from job_ingestion.runs import run_recorded_ingestion


def build_run(
    client: AdzunaClient,
    max_records: int,
    *,
    skill_alias_version: str | None = None,
) -> IngestionRun[AdzunaJobRecord]:
    """Assemble the stages around an already-built client.

    The lifetime a posting is kept for after it was last seen comes from the
    client's config, because the config is what windows every request; the
    client itself stays transport and never reads a job field.
    """
    return IngestionRun(
        client=client,
        validator=AdzunaValidator(),
        normalizer=AdzunaNormalizer(),
        source=SourceRegistration(
            key=SOURCE_KEY,
            display_name=DISPLAY_NAME,
            base_url=client.config.base_url,
            precedence=PRECEDENCE,
        ),
        max_records=max_records,
        skill_alias_version=skill_alias_version,
        retire_unseen_after=client.config.retire_unseen_after,
    )


async def ingest_adzuna(
    *,
    config: AdzunaConfig | None = None,
    max_records: int = DEFAULT_MAX_RECORDS,
    settings: Settings | None = None,
    http_client: httpx2.AsyncClient | None = None,
) -> IngestionSummary:
    """Run one complete Adzuna ingestion against the configured database.

    This is the entry point a scheduler calls. It owns the database engine, and
    the HTTP client unless one is supplied, and closes what it owns whatever the
    run reports.

    Credentials are resolved before anything else. `require` records the run
    itself when they are missing, and on the way through it installs log
    redaction and registers the key, so by the time the client below is built
    the key is already protected everywhere in the process. The client then
    reserves every call against the daily quota in a session of its own,
    opened from the same database the run writes to.
    """
    app_settings = settings if settings is not None else get_settings()
    database = Database(app_settings.database_url)
    resolved = config if config is not None else AdzunaConfig()
    started_at = datetime.now(UTC)

    try:
        credentials = await require(database, SOURCE_KEY, CREDENTIALS, started_at=started_at)
        if isinstance(credentials, IngestionSummary):
            return credentials

        async def build(database: Database) -> IngestionSummary:
            async with AdzunaClient(
                resolved, credentials, database.session, http_client=http_client
            ) as client:
                return await build_run(
                    client,
                    max_records,
                    skill_alias_version=app_settings.skill_alias_version,
                ).execute(database)

        return await run_recorded_ingestion(database, SOURCE_KEY, build, started_at=started_at)
    finally:
        await database.dispose()

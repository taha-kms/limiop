"""Wiring and entry point for the Himalayas ingestion run.

Everything reusable lives in `ingestion.pipeline`. This module only names the
concrete parts and owns their lifecycles, so a scheduler can start a run without
knowing any stage.
"""

from datetime import UTC, datetime

import httpx2

from job_ingestion.config import Settings, get_settings
from job_ingestion.contracts import IngestionSummary
from job_ingestion.database import Database
from job_ingestion.himalayas.client import (
    SOURCE_KEY,
    HimalayasClient,
    HimalayasConfig,
)
from job_ingestion.himalayas.normalizer import PRECEDENCE, HimalayasNormalizer
from job_ingestion.himalayas.records import HimalayasJobRecord, HimalayasValidator
from job_ingestion.persistence import SourceRegistration
from job_ingestion.pipeline import DEFAULT_MAX_RECORDS, IngestionRun
from job_ingestion.runs import run_recorded_ingestion

DISPLAY_NAME = "Himalayas"


def build_run(
    client: HimalayasClient,
    max_records: int,
    *,
    skill_alias_version: str | None = None,
) -> IngestionRun[HimalayasJobRecord]:
    """Assemble the stages around an already-built client."""
    return IngestionRun(
        client=client,
        validator=HimalayasValidator(),
        normalizer=HimalayasNormalizer(),
        source=SourceRegistration(
            key=SOURCE_KEY,
            display_name=DISPLAY_NAME,
            base_url=client.config.base_url,
            precedence=PRECEDENCE,
        ),
        max_records=max_records,
        skill_alias_version=skill_alias_version,
    )


def himalayas_run(
    config: HimalayasConfig | None = None,
    *,
    http_client: httpx2.AsyncClient | None = None,
    max_records: int = DEFAULT_MAX_RECORDS,
    skill_alias_version: str | None = None,
) -> IngestionRun[HimalayasJobRecord]:
    """Build a bounded Himalayas ingestion run around a caller-managed client."""
    settings = config if config is not None else HimalayasConfig()
    return build_run(
        HimalayasClient(settings, http_client=http_client),
        max_records,
        skill_alias_version=skill_alias_version,
    )


async def ingest_himalayas(
    *,
    config: HimalayasConfig | None = None,
    max_records: int = DEFAULT_MAX_RECORDS,
    settings: Settings | None = None,
    http_client: httpx2.AsyncClient | None = None,
) -> IngestionSummary:
    """Run one complete Himalayas ingestion against the configured database.

    This is the entry point a scheduler calls. It owns the database engine, and
    the HTTP client unless one is supplied, and closes what it owns whatever the
    run reports. The record/reconcile/complete sequence around the run itself
    lives in `run_recorded_ingestion`, shared with every other provider's
    entry point.
    """
    app_settings = settings if settings is not None else get_settings()
    database = Database(app_settings.database_url)
    resolved = config if config is not None else HimalayasConfig()
    started_at = datetime.now(UTC)

    async def build(database: Database) -> IngestionSummary:
        async with HimalayasClient(resolved, http_client=http_client) as client:
            return await build_run(
                client,
                max_records,
                skill_alias_version=app_settings.skill_alias_version,
            ).execute(database)

    try:
        return await run_recorded_ingestion(database, SOURCE_KEY, build, started_at=started_at)
    finally:
        await database.dispose()

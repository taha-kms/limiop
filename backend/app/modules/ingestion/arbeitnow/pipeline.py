"""Wiring and entry point for the Arbeitnow ingestion run.

Everything reusable lives in `ingestion.pipeline`. This module only names the
concrete parts and owns their lifecycles, so a scheduler can start a run without
knowing any stage.
"""

import httpx2

from app.core.config import Settings, get_settings
from app.db.session import Database
from app.modules.ingestion.arbeitnow.client import (
    SOURCE_KEY,
    ArbeitnowClient,
    ArbeitnowConfig,
)
from app.modules.ingestion.arbeitnow.normalizer import ArbeitnowNormalizer
from app.modules.ingestion.arbeitnow.records import ArbeitnowJobRecord, ArbeitnowValidator
from app.modules.ingestion.contracts import IngestionSummary
from app.modules.ingestion.persistence import SourceRegistration
from app.modules.ingestion.pipeline import DEFAULT_MAX_RECORDS, IngestionRun

DISPLAY_NAME = "Arbeitnow"

# Arbeitnow aggregates postings that employers publish on their own boards,
# so where the two disagree the board is the better account. Ranked below
# them, and above nothing, since it is the only source until one is added.
PRECEDENCE = 10


def build_run(client: ArbeitnowClient, max_records: int) -> IngestionRun[ArbeitnowJobRecord]:
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
    )


def arbeitnow_run(
    config: ArbeitnowConfig | None = None,
    *,
    http_client: httpx2.AsyncClient | None = None,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> IngestionRun[ArbeitnowJobRecord]:
    """Build a bounded Arbeitnow ingestion run around a caller-managed client."""
    settings = config if config is not None else ArbeitnowConfig()
    return build_run(ArbeitnowClient(settings, http_client=http_client), max_records)


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
    try:
        async with ArbeitnowClient(resolved, http_client=http_client) as client:
            return await build_run(client, max_records).execute(database)
    finally:
        await database.dispose()

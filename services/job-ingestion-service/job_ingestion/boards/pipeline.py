"""Wiring and entry point for any tenant-board provider's ingestion run.

Everything reusable lives in `ingestion.pipeline`. This module names the
concrete parts for one provider, owns their lifecycles, and folds in the
boards that could not be read, which the generic run has no way to learn
about.
"""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import httpx2

from job_ingestion.boards.client import BoardClient, BoardConfig
from job_ingestion.boards.provider import BoardProvider
from job_ingestion.config import Settings, get_settings
from job_ingestion.contracts import IngestionSummary
from job_ingestion.database import Database
from job_ingestion.persistence import SourceRegistration
from job_ingestion.pipeline import DEFAULT_MAX_RECORDS, IngestionRun
from job_ingestion.reconciliation import ReconciliationResult, reconcile
from job_ingestion.runs import complete_run, recorded_run

BOARDS_SETTING = "boards"
BASE_URL_SETTING = "base_url"


def build_run(
    client: BoardClient,
    max_records: int,
    *,
    skill_alias_version: str | None = None,
) -> IngestionRun[Any]:
    """Assemble the stages around an already-built client."""
    provider = client.provider
    return IngestionRun(
        client=client,
        validator=provider.validator,
        normalizer=provider.normalizer,
        source=SourceRegistration(
            key=provider.source_key,
            display_name=provider.display_name,
            base_url=client.base_url,
            precedence=provider.precedence,
        ),
        max_records=max_records,
        skill_alias_version=skill_alias_version,
    )


def configured_boards(provider: BoardProvider[Any], settings: Settings) -> tuple[str, ...]:
    """The boards to read, from configuration when it names any.

    An absent or empty list means the shipped default rather than no boards. A
    run that reads nothing looks exactly like a run whose every board went away,
    and only one of those is a deployment mistake worth reporting as one.

    A setting that is present but not a list of names is refused. Falling back
    would turn a typo into a run that quietly ingests the shipped list while the
    operator believes it is reading the boards they configured.
    """
    key = provider.source_key
    configured = settings.source_config.get(key, {}).get(BOARDS_SETTING)
    if configured is None:
        return provider.default_boards
    if not isinstance(configured, list):
        raise ValueError(f"{key}.{BOARDS_SETTING} must be a list of board names")
    names = tuple(name for name in configured if isinstance(name, str))
    if len(names) != len(configured):
        raise ValueError(f"{key}.{BOARDS_SETTING} must be a list of board names")
    # Blank names are left for BoardConfig to refuse, so what a board name may
    # be is decided in one place.
    return names or provider.default_boards


def configured_base_url(provider: BoardProvider[Any], settings: Settings) -> str:
    """The host to read from, when a deployment names one.

    A provider with regional hosts answers a tenant on only one of them, and
    which one is a fact about the deployment rather than about the code.
    """
    key = provider.source_key
    configured = settings.source_config.get(key, {}).get(BASE_URL_SETTING)
    if configured is None:
        return provider.default_base_url
    if not isinstance(configured, str) or not configured.strip():
        raise ValueError(f"{key}.{BASE_URL_SETTING} must be a URL")
    return configured.strip()


def default_config(provider: BoardProvider[Any], settings: Settings | None = None) -> BoardConfig:
    """The configuration a run uses when the caller supplies none."""
    resolved = settings if settings is not None else get_settings()
    return BoardConfig(
        boards=configured_boards(provider, resolved),
        base_url=configured_base_url(provider, resolved),
    )


def with_board_failures(summary: IngestionSummary, client: BoardClient) -> IngestionSummary:
    """Add the boards that could not be read to what the run reports.

    The generic run only sees the pages it was handed, so a board skipped by the
    client would otherwise vanish from the summary and the run would look
    complete while a company was missing entirely.
    """
    if not client.failures:
        return summary
    return replace(summary, failures=summary.failures + tuple(client.failures))


async def ingest_board_source(
    provider: BoardProvider[Any],
    *,
    config: BoardConfig | None = None,
    max_records: int = DEFAULT_MAX_RECORDS,
    settings: Settings | None = None,
    http_client: httpx2.AsyncClient | None = None,
) -> IngestionSummary:
    """Run one complete ingestion of one provider against the configured database."""
    app_settings = settings if settings is not None else get_settings()
    database = Database(app_settings.database_url)
    resolved = config if config is not None else default_config(provider, app_settings)
    started_at = datetime.now(UTC)
    try:
        async with recorded_run(database, provider.source_key) as run_id:
            async with BoardClient(provider, resolved, http_client=http_client) as client:
                summary = with_board_failures(
                    await build_run(
                        client,
                        max_records,
                        skill_alias_version=app_settings.skill_alias_version,
                    ).execute(database),
                    client,
                )
            await reconcile_after(database, summary, run_started_at=started_at)
        await complete_run(database, run_id, summary)
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

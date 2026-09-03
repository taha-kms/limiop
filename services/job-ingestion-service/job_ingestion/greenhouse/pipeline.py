"""Greenhouse's entry point, kept as an import path over the generic one.

The wiring is the same for every tenant-board provider and lives in
`boards.pipeline`. These names survive because the DAG, the tests, and a
caller that only wants Greenhouse use them.
"""

from typing import Any

import httpx2

from job_ingestion.boards import pipeline as boards
from job_ingestion.boards.client import BoardClient
from job_ingestion.boards.pipeline import BOARDS_SETTING, with_board_failures
from job_ingestion.config import Settings, get_settings
from job_ingestion.contracts import IngestionSummary
from job_ingestion.greenhouse.client import GreenhouseConfig
from job_ingestion.greenhouse.provider import GREENHOUSE
from job_ingestion.greenhouse.source import (
    DEFAULT_BASE_URL,
    DEFAULT_BOARDS,
    DISPLAY_NAME,
    PRECEDENCE,
    SOURCE_KEY,
)
from job_ingestion.pipeline import DEFAULT_MAX_RECORDS, IngestionRun


def build_run(
    client: BoardClient,
    max_records: int,
    *,
    skill_alias_version: str | None = None,
) -> IngestionRun[Any]:
    return boards.build_run(client, max_records, skill_alias_version=skill_alias_version)


def configured_boards(settings: Settings) -> tuple[str, ...]:
    return boards.configured_boards(GREENHOUSE, settings)


def default_config(settings: Settings | None = None) -> GreenhouseConfig:
    resolved = settings if settings is not None else get_settings()
    return GreenhouseConfig(
        boards=boards.configured_boards(GREENHOUSE, resolved),
        base_url=boards.configured_base_url(GREENHOUSE, resolved),
    )


async def ingest_greenhouse(
    *,
    config: GreenhouseConfig | None = None,
    max_records: int = DEFAULT_MAX_RECORDS,
    settings: Settings | None = None,
    http_client: httpx2.AsyncClient | None = None,
) -> IngestionSummary:
    """Run one complete Greenhouse ingestion against the configured database."""
    return await boards.ingest_board_source(
        GREENHOUSE,
        config=config,
        max_records=max_records,
        settings=settings,
        http_client=http_client,
    )


__all__ = [
    "BOARDS_SETTING",
    "DEFAULT_BASE_URL",
    "DEFAULT_BOARDS",
    "DISPLAY_NAME",
    "PRECEDENCE",
    "SOURCE_KEY",
    "build_run",
    "configured_boards",
    "default_config",
    "ingest_greenhouse",
    "with_board_failures",
]

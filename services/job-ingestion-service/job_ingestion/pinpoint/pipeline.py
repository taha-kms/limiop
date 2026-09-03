"""Pinpoint's entry point, kept as an import path over the generic one.

Everything a run needs lives in `boards.pipeline`. This module names the one
thing a caller wanting only Pinpoint would otherwise have to know the
registry for.
"""

import httpx2

from job_ingestion.boards import pipeline as boards
from job_ingestion.boards.client import BoardConfig
from job_ingestion.config import Settings
from job_ingestion.contracts import IngestionSummary
from job_ingestion.pinpoint.provider import PINPOINT
from job_ingestion.pipeline import DEFAULT_MAX_RECORDS


async def ingest_pinpoint(
    *,
    config: BoardConfig | None = None,
    max_records: int = DEFAULT_MAX_RECORDS,
    settings: Settings | None = None,
    http_client: httpx2.AsyncClient | None = None,
) -> IngestionSummary:
    """Run one complete Pinpoint ingestion against the configured database."""
    return await boards.ingest_board_source(
        PINPOINT,
        config=config,
        max_records=max_records,
        settings=settings,
        http_client=http_client,
    )


__all__ = ["ingest_pinpoint"]

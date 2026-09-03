"""Polymer's entry point, kept as an import path over the generic one.

Everything a run needs lives in `boards.pipeline`, keyed by the provider
value. This module names the one thing a caller wanting only Polymer would
otherwise have to know the registry for.
"""

import httpx2

from job_ingestion.boards import pipeline as boards
from job_ingestion.boards.client import BoardConfig
from job_ingestion.config import Settings
from job_ingestion.contracts import IngestionSummary
from job_ingestion.pipeline import DEFAULT_MAX_RECORDS
from job_ingestion.polymer.provider import POLYMER


async def ingest_polymer(
    *,
    config: BoardConfig | None = None,
    max_records: int = DEFAULT_MAX_RECORDS,
    settings: Settings | None = None,
    http_client: httpx2.AsyncClient | None = None,
) -> IngestionSummary:
    """Run one complete Polymer ingestion against the configured database."""
    return await boards.ingest_board_source(
        POLYMER,
        config=config,
        max_records=max_records,
        settings=settings,
        http_client=http_client,
    )


__all__ = ["ingest_polymer"]

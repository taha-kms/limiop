"""Wiring for the Arbeitnow ingestion run.

Everything reusable lives in `ingestion.pipeline`. This module only names the
concrete parts, so a scheduler can start a run without knowing any stage.
"""

import httpx2

from app.modules.ingestion.arbeitnow.client import (
    SOURCE_KEY,
    ArbeitnowClient,
    ArbeitnowConfig,
)
from app.modules.ingestion.arbeitnow.normalizer import ArbeitnowNormalizer
from app.modules.ingestion.arbeitnow.records import ArbeitnowJobRecord, ArbeitnowValidator
from app.modules.ingestion.persistence import SourceRegistration
from app.modules.ingestion.pipeline import DEFAULT_MAX_RECORDS, IngestionRun

DISPLAY_NAME = "Arbeitnow"


def arbeitnow_run(
    config: ArbeitnowConfig | None = None,
    *,
    http_client: httpx2.AsyncClient | None = None,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> IngestionRun[ArbeitnowJobRecord]:
    """Build a bounded Arbeitnow ingestion run."""
    settings = config if config is not None else ArbeitnowConfig()
    return IngestionRun(
        client=ArbeitnowClient(settings, http_client=http_client),
        validator=ArbeitnowValidator(),
        normalizer=ArbeitnowNormalizer(),
        source=SourceRegistration(
            key=SOURCE_KEY,
            display_name=DISPLAY_NAME,
            base_url=settings.base_url,
        ),
        max_records=max_records,
    )

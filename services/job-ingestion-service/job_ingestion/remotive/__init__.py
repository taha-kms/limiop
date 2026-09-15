"""Remotive remote job board provider."""

from job_ingestion.remotive.client import (
    DEFAULT_BASE_URL,
    SOURCE_KEY,
    RemotiveClient,
    RemotiveConfig,
)
from job_ingestion.remotive.normalizer import RemotiveNormalizer
from job_ingestion.remotive.pipeline import (
    DISPLAY_NAME,
    ingest_remotive,
    remotive_run,
)
from job_ingestion.remotive.records import RemotiveJobRecord, RemotiveValidator

__all__ = [
    "DEFAULT_BASE_URL",
    "DISPLAY_NAME",
    "SOURCE_KEY",
    "RemotiveClient",
    "RemotiveConfig",
    "RemotiveJobRecord",
    "RemotiveNormalizer",
    "RemotiveValidator",
    "ingest_remotive",
    "remotive_run",
]

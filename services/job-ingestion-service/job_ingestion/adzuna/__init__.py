"""Adzuna licensed aggregator provider."""

from job_ingestion.adzuna.normalizer import AdzunaNormalizer
from job_ingestion.adzuna.records import AdzunaJobRecord, AdzunaValidator
from job_ingestion.adzuna.source import (
    CREDENTIALS,
    DAILY_QUOTA,
    DEFAULT_BASE_URL,
    DEFAULT_COUNTRIES,
    DISPLAY_NAME,
    PRECEDENCE,
    SOURCE_KEY,
)

__all__ = [
    "CREDENTIALS",
    "DAILY_QUOTA",
    "DEFAULT_BASE_URL",
    "DEFAULT_COUNTRIES",
    "DISPLAY_NAME",
    "PRECEDENCE",
    "SOURCE_KEY",
    "AdzunaJobRecord",
    "AdzunaNormalizer",
    "AdzunaValidator",
]

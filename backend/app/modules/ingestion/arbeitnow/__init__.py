"""Arbeitnow job board provider."""

from app.modules.ingestion.arbeitnow.client import (
    DEFAULT_BASE_URL,
    SOURCE_KEY,
    ArbeitnowClient,
    ArbeitnowConfig,
)
from app.modules.ingestion.arbeitnow.normalizer import ArbeitnowNormalizer
from app.modules.ingestion.arbeitnow.records import ArbeitnowJobRecord, ArbeitnowValidator

__all__ = [
    "DEFAULT_BASE_URL",
    "SOURCE_KEY",
    "ArbeitnowClient",
    "ArbeitnowConfig",
    "ArbeitnowJobRecord",
    "ArbeitnowNormalizer",
    "ArbeitnowValidator",
]

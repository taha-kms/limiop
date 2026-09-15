"""Jobicy remote-jobs provider."""

from job_ingestion.jobicy.client import (
    DEFAULT_BASE_URL,
    SOURCE_KEY,
    JobicyClient,
    JobicyConfig,
)
from job_ingestion.jobicy.normalizer import PRECEDENCE, JobicyNormalizer
from job_ingestion.jobicy.pipeline import DISPLAY_NAME, build_run, ingest_jobicy
from job_ingestion.jobicy.records import JobicyJobRecord, JobicyValidator

__all__ = [
    "DEFAULT_BASE_URL",
    "DISPLAY_NAME",
    "PRECEDENCE",
    "SOURCE_KEY",
    "JobicyClient",
    "JobicyConfig",
    "JobicyJobRecord",
    "JobicyNormalizer",
    "JobicyValidator",
    "build_run",
    "ingest_jobicy",
]

"""Greenhouse job board provider."""

from job_ingestion.greenhouse.pipeline import ingest_greenhouse

__all__ = ["ingest_greenhouse"]

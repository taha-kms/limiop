"""Greenhouse board discovery, kept as an import path.

The mechanism is provider-agnostic and lives in `boards.discovery`. Nothing
here is Greenhouse's own; the module survives so existing callers keep
working.
"""

from job_ingestion.boards.discovery import (
    LEGAL_SUFFIXES,
    DiscoveryOutcome,
    DiscoveryResult,
    belongs_to,
    candidate_slugs,
    discover,
    strip_legal_form,
)

__all__ = [
    "LEGAL_SUFFIXES",
    "DiscoveryOutcome",
    "DiscoveryResult",
    "belongs_to",
    "candidate_slugs",
    "discover",
    "strip_legal_form",
]

"""Domain types and normalization rules for the job catalog."""

import unicodedata


def normalize_company_name(value: str) -> str:
    """Apply NFKC, case-fold, and collapse whitespace while preserving punctuation."""
    normalized = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    if not normalized:
        raise ValueError("company name must contain non-whitespace characters")
    return normalized

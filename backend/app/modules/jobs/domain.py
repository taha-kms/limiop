"""Domain types and normalization rules for the job catalog."""

import unicodedata
from enum import StrEnum


class WorkplaceType(StrEnum):
    """Canonical workplace arrangement.

    REMOTE means work is performed away from an employer site. HYBRID combines
    remote and employer-site work. ONSITE requires employer-site work.
    UNSPECIFIED is the fallback for missing or unknown provider values.
    """

    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNSPECIFIED = "unspecified"


class EmploymentType(StrEnum):
    """Canonical employment relationship.

    FULL_TIME and PART_TIME describe employee schedules. CONTRACT describes
    contract work, INTERNSHIP describes a training placement, and TEMPORARY
    describes time-limited employment. UNSPECIFIED is the fallback for missing
    or unknown provider values.
    """

    FULL_TIME = "full-time"
    PART_TIME = "part-time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"
    UNSPECIFIED = "unspecified"


class JobStatus(StrEnum):
    """Canonical job lifecycle state.

    ACTIVE jobs are listable, EXPIRED jobs passed their stated lifetime, and
    REMOVED jobs were withdrawn or disappeared under a trusted lifecycle rule.
    """

    ACTIVE = "active"
    EXPIRED = "expired"
    REMOVED = "removed"


def normalize_company_name(value: str) -> str:
    """Apply NFKC, case-fold, and collapse whitespace while preserving punctuation."""
    normalized = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    if not normalized:
        raise ValueError("company name must contain non-whitespace characters")
    return normalized

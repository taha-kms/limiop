"""Domain types and normalization rules for the job catalog."""

import unicodedata
from enum import StrEnum

EXCERPT_LENGTH = 200
ELLIPSIS = "\u2026"


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


def to_excerpt(description: str, *, limit: int = EXCERPT_LENGTH) -> str:
    """Reduce a description to something a listing card can show.

    Derived rather than stored, so it cannot fall out of step with the
    description it summarises.

    Paragraphs are joined rather than stopping at the first one. Stopping there
    was the original rule and real postings disproved it: they routinely open
    with a heading, so the excerpt came out as `Why Mozilla?` or
    `About Team & About Role`, which is a label rather than a summary. Joining
    lets a short opening line be followed by the prose that explains it.

    Past the limit it cuts at a word boundary, because a word sliced in half
    reads as a bug. Text with no space to cut at is cut on length alone: it
    still has to come back bounded, which is the case a word boundary cannot
    serve.
    """
    paragraphs = (line.strip() for line in description.split("\n"))
    joined = " ".join(line for line in paragraphs if line)
    if len(joined) <= limit:
        return joined

    head = joined[:limit]
    if joined[limit].isspace():
        # The cut already landed between words, so trimming back to the last
        # space here would drop a whole word that fitted.
        return f"{head.rstrip()}{ELLIPSIS}"

    cut = head.rfind(" ")
    return f"{head if cut < 1 else head[:cut]}{ELLIPSIS}"


def normalize_company_name(value: str) -> str:
    """Apply NFKC, case-fold, and collapse whitespace while preserving punctuation."""
    normalized = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    if not normalized:
        raise ValueError("company name must contain non-whitespace characters")
    return normalized

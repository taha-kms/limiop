"""Domain types and normalization rules for the job catalog."""

from platform_db.models.catalog import (
    EmploymentType,
    JobStatus,
    WorkplaceType,
    normalize_company_name,
)

EXCERPT_LENGTH = 200
ELLIPSIS = "\u2026"

__all__ = [
    "ELLIPSIS",
    "EXCERPT_LENGTH",
    "EmploymentType",
    "JobStatus",
    "WorkplaceType",
    "normalize_company_name",
    "to_excerpt",
]


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

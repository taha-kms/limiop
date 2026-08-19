"""Deterministic identity for a canonical job.

A fingerprint answers one question: do two normalized jobs describe the same
posting? It is computed from canonical fields only, so the same posting fetched
from two providers fingerprints identically.

Versioning
----------

Every fingerprint carries the version of the rules that produced it. Changing
any rule below means bumping `FINGERPRINT_VERSION`, after which old and new
fingerprints no longer compare equal and stored values must be recomputed.

Inputs (version v1)
-------------------

- the company's normalized name
- the normalized job title
- the normalized location, or an empty part when the job has none

Deliberately excluded: description, because employers reword it without
reposting; URLs, because they differ per provider for the same posting;
timestamps, because a repost of the same job would otherwise look new.
"""

import re
import unicodedata
from hashlib import sha256

from app.modules.jobs.domain import normalize_company_name
from app.modules.jobs.schemas import NormalizedJob

FINGERPRINT_VERSION = "v1"

# Parts are joined with the ASCII unit separator, which normalization strips
# from the parts themselves. Without it, ("ab", "c") and ("a", "bc") would
# produce the same input string and collide.
PART_SEPARATOR = "\x1f"

# German-market listings routinely append a gender notation to the title. The
# same posting appears as both "Data Engineer" and "Data Engineer (m/w/d)", so
# the notation is dropped before hashing.
GENDER_NOTATION = re.compile(
    r"\(\s*(?:[mwfdax](?:\s*[/|]\s*[mwfdax])+|all\s+genders?|any\s+gender)\s*\)",
    re.IGNORECASE,
)


def normalize_text(value: str) -> str:
    """Apply NFKC, case-fold, and collapse whitespace and control characters."""
    folded = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(folded.split())


def normalize_title(value: str) -> str:
    """Normalize a title and drop gender notation that does not change the role."""
    return normalize_text(GENDER_NOTATION.sub(" ", value))


def fingerprint_parts(job: NormalizedJob) -> tuple[str, str, str]:
    """Return the exact values that a fingerprint is computed from."""
    return (
        normalize_company_name(job.company.display_name),
        normalize_title(job.title),
        normalize_text(job.location) if job.location else "",
    )


def fingerprint(job: NormalizedJob) -> str:
    """Return the versioned fingerprint of one normalized job."""
    joined = PART_SEPARATOR.join(fingerprint_parts(job))
    digest = sha256(joined.encode("utf-8")).hexdigest()
    return f"{FINGERPRINT_VERSION}:{digest}"

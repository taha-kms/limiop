"""Deciding whether two records describe the same posting.

Identity is a two-stage test, and neither stage is sufficient alone.

**The match key** blocks candidates. It is computed from the employer and the
title only, and it is deliberately loose: it answers "might these be the same
posting", not "are they". A single hash cannot answer the second question,
because the sources disagree about the fields that would settle it.

**Place and text** decide among the candidates. Two records are the same
posting when they name the same places and read the same way.

Why location left the key
-------------------------

Measured across twenty-nine cross-source duplicates confirmed by their text:
every single one described its location differently. `London` against
`London, UK`; `Berlin, Berlin` against `Berlin, Berlin, Germany`. An aggregator
drops the country the employer's own board keeps. A key containing the location
therefore matched none of them.

Removing it entirely is worse: replaying ten thousand postings showed two
thousand distinct openings collapsing into each other, because one employer
lists the same role in Seoul, Tokyo, Sydney and Mumbai and those are four jobs.

So the place is compared rather than hashed, on the city each side names.

Why the text is checked at all
------------------------------

Comparing cities alone still merged distinct requisitions that share a city:
two Staff Engineer openings in Dublin, with different descriptions. Nothing in
the employer, title or place separates them. Requiring the descriptions to
agree removed every measured wrong merge.

That check assumes sources carry the employer's own words. Both current sources
do, and their confirmed duplicates overlap by no less than `0.966`. A source
that wrote its own summaries would fail this and its duplicates would be missed,
so this is an assumption about how a source obtains its text, not a constant.

Versioning
----------

Every key carries the version of the rules that produced it. Changing any rule
means bumping `MATCH_KEY_VERSION`, after which old and new keys no longer
compare equal and stored values must be recomputed.
"""

import re
import unicodedata
from hashlib import sha256

from platform_db.models.catalog import normalize_company_name

from job_ingestion.schemas import NormalizedJob

MATCH_KEY_VERSION = "v2"

# Parts are joined with the ASCII unit separator, which normalization strips
# from the parts themselves. Without it, ("ab", "c") and ("a", "bc") would
# produce the same input string and collide.
PART_SEPARATOR = "\x1f"

# German-market listings routinely append a gender notation to the title. The
# same posting appears as both "Data Engineer" and "Data Engineer (m/w/d)", so
# the notation is dropped before hashing.
#
# Two patterns rather than one alternation: the letter form and the spelled-out
# form share nothing, and expressing them together produced an expression
# nobody could read.
LETTER_NOTATION = re.compile(r"\(\s*[mwfdax](?:\s*[/|]\s*[mwfdax])+\s*\)", re.IGNORECASE)
SPELLED_NOTATION = re.compile(r"\(\s*(?:all|any)\s+genders?\s*\)", re.IGNORECASE)

# Words that describe how work happens rather than where it happens. A location
# reading only "Remote" names no place at all.
NON_PLACES = frozenset(
    {
        "remote",
        "hybrid",
        "onsite",
        "on site",
        "home office",
        "homeoffice",
        "vor ort",
        "telearbeit",
        "flexible",
        "anywhere",
        "worldwide",
    }
)

# Hyphen, en dash, and em dash, written as escapes because a literal dash of
# each kind is indistinguishable in most editors.
LEADING_ARRANGEMENT = re.compile(
    "^(remote|hybrid|onsite|on site)\\s*[-\u2013\u2014]\\s*",
    re.IGNORECASE,
)

# Sources separate several places with a semicolon. A comma usually separates a
# city from its region and country instead, except where each place carries its
# own parenthesised country, which is the one shape that needs both.
PLACE_SEPARATOR = ";"

# Confirmed duplicates overlap by at least 0.966; measured wrong merges reached
# 0.82. Anywhere in between separates them, and the value is not delicate:
# recall was unchanged from 0.0 to 0.95.
MINIMUM_TEXT_OVERLAP = 0.85


def normalize_text(value: str) -> str:
    """Apply NFKC, case-fold, and collapse whitespace and control characters."""
    folded = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(folded.split())


def normalize_title(value: str) -> str:
    """Normalize a title and drop gender notation that does not change the role."""
    without_notation = SPELLED_NOTATION.sub(" ", LETTER_NOTATION.sub(" ", value))
    return normalize_text(without_notation)


def match_key_of(company_name: str, title: str) -> str:
    """The versioned key that blocks candidates for one employer and role."""
    joined = PART_SEPARATOR.join((normalize_company_name(company_name), normalize_title(title)))
    digest = sha256(joined.encode("utf-8")).hexdigest()
    return f"{MATCH_KEY_VERSION}:{digest}"


def match_key(job: NormalizedJob) -> str:
    """The versioned key of one normalized job."""
    return match_key_of(job.company.display_name, job.title)


def city_names(location: str | None) -> frozenset[str]:
    """The cities a location names, without regions, countries, or arrangements.

    An arrangement word is not a place, so `Remote, France` names France rather
    than nothing: skipping the word instead of the whole entry is what keeps
    `Remote, France` and `Remote, Spain` apart.
    """
    text = location or ""
    entries = [
        entry
        for chunk in text.split(PLACE_SEPARATOR)
        for entry in (chunk.split(",") if "(" in chunk else [chunk])
    ]

    found: set[str] = set()
    for entry in entries:
        for segment in re.sub(r"\([^)]*\)", " ", entry).split(","):
            name = normalize_text(LEADING_ARRANGEMENT.sub("", segment))
            if name and name not in NON_PLACES:
                # The first real name in an entry is its city; what follows is
                # the region and country the other source may have dropped.
                found.add(name)
                break
    return frozenset(found)


def same_place(stored: str | None, incoming: str | None) -> bool:
    """Whether two locations name the same cities.

    A side naming no city matches anything, because it has made no claim to
    contradict. That is common: one source says only `Remote` while the other
    says `Remote, United Kingdom`.
    """
    here, there = city_names(stored), city_names(incoming)
    if not here or not there:
        return True
    return here == there


def text_overlap(stored: str, incoming: str) -> float:
    """How much vocabulary two descriptions share, between 0 and 1."""
    here = set(re.findall(r"\w+", stored.casefold()))
    there = set(re.findall(r"\w+", incoming.casefold()))
    if not here or not there:
        return 0.0
    return len(here & there) / len(here | there)


def reads_the_same(stored: str, incoming: str) -> bool:
    """Whether two descriptions are the same posting rather than a similar one."""
    return text_overlap(stored, incoming) >= MINIMUM_TEXT_OVERLAP

"""Reading canonical vocabularies out of provider text.

Providers name the same arrangement in their own words, in their own fields,
and in more than one language. Every provider needs the same question answered
of whatever text it happens to carry: does this name an arrangement, and which.

Kept out of any provider module so a second one cannot drift from the first.
The rule that only explicit words count, and that silence is never read as
`onsite` or `full-time`, belongs to the domain rather than to whoever asks.
"""

import re
from collections.abc import Mapping
from enum import StrEnum

from platform_db.models.catalog import EmploymentType, WorkplaceType

# Phrases naming a workplace arrangement, in the languages the sources publish
# in. Keys are tokenized, so a phrase written with a hyphen, an underscore, or
# extra spacing resolves to the same entry.
WORKPLACE_BY_PHRASE: dict[str, WorkplaceType] = {
    "remote": WorkplaceType.REMOTE,
    "fully remote": WorkplaceType.REMOTE,
    "home office": WorkplaceType.REMOTE,
    "homeoffice": WorkplaceType.REMOTE,
    "telearbeit": WorkplaceType.REMOTE,
    "hybrid": WorkplaceType.HYBRID,
    "teilweise remote": WorkplaceType.HYBRID,
    "on site": WorkplaceType.ONSITE,
    "onsite": WorkplaceType.ONSITE,
    "in office": WorkplaceType.ONSITE,
    "vor ort": WorkplaceType.ONSITE,
    "präsenz": WorkplaceType.ONSITE,
}

# Hybrid outranks remote because it is the more specific claim: it asserts both
# arrangements, so a posting described as each is hybrid.
WORKPLACE_PRECEDENCE = (
    WorkplaceType.HYBRID,
    WorkplaceType.REMOTE,
    WorkplaceType.ONSITE,
)

EMPLOYMENT_BY_PHRASE: dict[str, EmploymentType] = {
    "full time": EmploymentType.FULL_TIME,
    "fulltime": EmploymentType.FULL_TIME,
    "vollzeit": EmploymentType.FULL_TIME,
    "part time": EmploymentType.PART_TIME,
    "parttime": EmploymentType.PART_TIME,
    "teilzeit": EmploymentType.PART_TIME,
    "contract": EmploymentType.CONTRACT,
    "contractor": EmploymentType.CONTRACT,
    "freelance": EmploymentType.CONTRACT,
    "internship": EmploymentType.INTERNSHIP,
    "intern": EmploymentType.INTERNSHIP,
    "praktikum": EmploymentType.INTERNSHIP,
    "working student": EmploymentType.INTERNSHIP,
    "werkstudent": EmploymentType.INTERNSHIP,
    "temporary": EmploymentType.TEMPORARY,
    "temp": EmploymentType.TEMPORARY,
    "fixed term": EmploymentType.TEMPORARY,
    "befristet": EmploymentType.TEMPORARY,
}

# The most specific relationship wins, so an internship advertised as part time
# is not filed as ordinary part-time work.
EMPLOYMENT_PRECEDENCE = (
    EmploymentType.INTERNSHIP,
    EmploymentType.TEMPORARY,
    EmploymentType.CONTRACT,
    EmploymentType.PART_TIME,
    EmploymentType.FULL_TIME,
)


def to_token(value: str) -> str:
    """Reduce a provider label to a comparable token."""
    return " ".join(value.replace("_", " ").replace("-", " ").casefold().split())


def build_pattern(phrases: Mapping[str, object]) -> re.Pattern[str]:
    """Match any phrase as whole words, longest first.

    Longest first so `teilweise remote` reads as hybrid rather than matching
    `remote` inside it. Word boundaries stop a phrase being found inside an
    unrelated word, which is what keeps Bremen out of remote work.
    """
    alternatives = "|".join(
        re.escape(phrase).replace(r"\ ", r"[\s_-]+")
        for phrase in sorted(phrases, key=len, reverse=True)
    )
    return re.compile(rf"\b(?:{alternatives})\b", re.IGNORECASE)


WORKPLACE_PATTERN = build_pattern(WORKPLACE_BY_PHRASE)
EMPLOYMENT_PATTERN = build_pattern(EMPLOYMENT_BY_PHRASE)


def stated_workplaces(*texts: str | None) -> set[WorkplaceType]:
    """Every workplace arrangement the given text names outright."""
    return {
        WORKPLACE_BY_PHRASE[to_token(match)]
        for text in texts
        if text
        for match in WORKPLACE_PATTERN.findall(text)
    }


def stated_employments(*texts: str | None) -> set[EmploymentType]:
    """Every employment relationship the given text names outright."""
    return {
        EMPLOYMENT_BY_PHRASE[to_token(match)]
        for text in texts
        if text
        for match in EMPLOYMENT_PATTERN.findall(text)
    }


def most_specific[MemberT: StrEnum](
    stated: set[MemberT],
    precedence: tuple[MemberT, ...],
    fallback: MemberT,
) -> MemberT:
    """The most specific member named, or the fallback when none was.

    The fallback is reached only by silence. Nothing here infers an arrangement
    from the absence of a word, because a posting that says nothing about where
    the work happens has not said it happens in an office.
    """
    for candidate in precedence:
        if candidate in stated:
            return candidate
    return fallback

"""Finding a company's board without anyone typing its name.

What the stored data cannot do
------------------------------

The obvious mechanism does not work here. A company was expected to carry an
application URL naming its applicant tracking system, but measured over the
stored catalogue exactly one company's URL names Greenhouse — the one already
configured by hand. Every Arbeitnow posting points at `arbeitnow.com`, because
the aggregator rewrites the link to its own page, and its payload carries
`company_name`, `slug`, `title`, `location`, `tags` and no employer URL at all.

So there is nothing to read a board out of, and the only input left is the
company's name. That means guessing, which the issue rightly calls one input
rather than the answer.

What makes a guess safe
-----------------------

Verification, which is the half worth building. A board states the company
it belongs to on every posting it returns, so a guess can be checked against
the company it was derived from before a single record is ingested. A slug
that resolves to somebody else is rejected and reported, not stored.

That inverts the risk. Guessing wrongly is cheap and visible; guessing wrongly
and ingesting is how a company's postings end up filed under another employer,
which is the failure the hand-written board list existed to avoid.

Not every feed states a company. Where it does not, a guess that answers can
be reported and cannot be confirmed, and that is its own outcome rather than
a weaker confirmation. Adding such a board stays a deliberate act by someone
who looked at the careers page.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from platform_db.models.catalog import normalize_company_name

from job_ingestion.errors import SourceResponseError, SourceUnavailableError

if TYPE_CHECKING:
    from job_ingestion.boards.client import BoardClient

# Suffixes that name a legal form rather than the company. A board slug almost
# never carries one, and leaving them in turns "Acme GmbH" into a slug nothing
# answers.
LEGAL_SUFFIXES = (
    "gmbh & co kg",
    "gmbh",
    "ag",
    "se",
    "ug",
    "kg",
    "ohg",
    "inc",
    "llc",
    "ltd",
    "limited",
    "plc",
    "bv",
    "nv",
    "sa",
    "srl",
    "oy",
    "ab",
    "as",
)

_SEPARATORS = re.compile(r"[^a-z0-9]+")
# Trailing punctuation, so `Example Ltd.` matches the same suffix as
# `Example Ltd`. The normalizer keeps it, and a suffix list that did not
# tolerate it would silently miss the commonest written form.
_TRAILING_PUNCTUATION = " \t.,;:-"


class DiscoveryOutcome(StrEnum):
    """What checking one candidate slug established."""

    CONFIRMED = "confirmed"
    # The board answered and belongs to somebody else. The single outcome the
    # hand-written list existed to prevent.
    WRONG_COMPANY = "wrong_company"
    # The board answered with postings and the feed states no company, so
    # nothing here can say whose they are.
    UNVERIFIABLE = "unverifiable"
    NOT_FOUND = "not_found"
    UNREACHABLE = "unreachable"


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """One company, and what was learned about its board."""

    company: str
    outcome: DiscoveryOutcome
    slug: str | None = None
    found_company: str | None = None


def strip_legal_form(name: str) -> str:
    """Drop a trailing legal suffix, however it was punctuated.

    A blank name is empty rather than an error. The catalogue's normalizer
    refuses one because a company row must have a name, but discovery is handed
    whatever is stored and answering "nothing to guess from" is more useful
    than raising.
    """
    if not name.strip():
        return ""
    normalized = normalize_company_name(name).rstrip(_TRAILING_PUNCTUATION)
    for suffix in LEGAL_SUFFIXES:
        if normalized.endswith(f" {suffix}"):
            return normalized[: -len(suffix) - 1].rstrip(_TRAILING_PUNCTUATION)
    return normalized


def candidate_slugs(company_name: str) -> tuple[str, ...]:
    """Slugs a company of this name might use, most likely first.

    Ordered rather than scored: each is checked against the board it names, so
    a wrong guess costs one request and is caught. Ordering only decides which
    request is made first.
    """
    stripped = strip_legal_form(company_name)
    if not stripped:
        return ()

    joined = _SEPARATORS.sub("", stripped)
    hyphenated = _SEPARATORS.sub("-", stripped).strip("-")
    first = stripped.split(" ")[0]

    seen: dict[str, None] = {}
    for slug in (joined, hyphenated, first):
        if slug and slug not in seen:
            seen[slug] = None
    return tuple(seen)


def belongs_to(found_company: str, expected_company: str) -> bool:
    """Whether a board's stated company is the one we were looking for.

    Compared after the deduplication key's normalization, after dropping the
    legal form, and after removing separators. The first two because a board
    says `Acme` where the aggregator said `Acme GmbH`; the third because they
    also disagree about spacing — the aggregator stored `wppmedia` where the
    board says `WPP Media`, and treating that as a different company rejects a
    board that is plainly the right one.

    Separators are the only thing ignored. `Acme Health` and `Acme` stay
    different, which is what keeps this from confirming a board by coincidence.
    """
    return _SEPARATORS.sub("", strip_legal_form(found_company)) == _SEPARATORS.sub(
        "", strip_legal_form(expected_company)
    )


async def discover(client: "BoardClient", company_name: str) -> DiscoveryResult:
    """Check this company's candidate slugs until one is confirmed.

    Stops at the first confirmation. A board that answers for somebody else is
    reported rather than tried again with a looser rule — a second attempt to
    make a wrong answer fit is how a company's postings end up under another
    employer's name.
    """
    slugs = candidate_slugs(company_name)
    if not slugs:
        return DiscoveryResult(company=company_name, outcome=DiscoveryOutcome.NOT_FOUND)

    mismatch: DiscoveryResult | None = None
    unreachable: DiscoveryResult | None = None
    for slug in slugs:
        try:
            page = await client.fetch_board(slug)
        except SourceResponseError:
            # The board does not exist, which is the ordinary answer for a
            # guess and says nothing about the next one.
            continue
        except SourceUnavailableError:
            unreachable = DiscoveryResult(
                company=company_name, outcome=DiscoveryOutcome.UNREACHABLE, slug=slug
            )
            continue

        if not page.records:
            # An empty board states nothing, and a board that states nothing
            # cannot confirm anything.
            continue
        found = client.provider.stated_company(page.records)
        if found is None:
            # Nothing further can be learned from this provider about any
            # slug, so the search ends where it is.
            return DiscoveryResult(
                company=company_name, outcome=DiscoveryOutcome.UNVERIFIABLE, slug=slug
            )
        if belongs_to(found, company_name):
            return DiscoveryResult(
                company=company_name,
                outcome=DiscoveryOutcome.CONFIRMED,
                slug=slug,
                found_company=found,
            )
        mismatch = DiscoveryResult(
            company=company_name,
            outcome=DiscoveryOutcome.WRONG_COMPANY,
            slug=slug,
            found_company=found,
        )

    # A wrong company outranks silence in the report: it is the one outcome a
    # reader has to act on, because it names a slug that must never be polled.
    return (
        mismatch
        or unreachable
        or DiscoveryResult(company=company_name, outcome=DiscoveryOutcome.NOT_FOUND)
    )

"""Removing what an employer repeats about itself.

Pure and deterministic: the same postings always produce the same text, and
nothing here touches the network or the database.

The problem is measurable rather than aesthetic. One employer contributes half
this catalogue and closes every posting with the same blurb about itself, so
its self-description is a large fraction of everything the candidate generator
proposes: `San` from "headquartered in San Francisco", `Concrete` and `Neurons`
from a list of that employer's own papers, `anthropic.com/careers` from an
anti-scam notice.

Repetition alone does not license removal, because an employer whose postings
share a real requirement repeats that too. The second signal is what the block
is about: a block that names the employer is the employer talking about itself,
and a requirement talks about the role. Measured over the 25 employers in this
catalogue with enough postings to establish a pattern, that rule drops 51 blocks
across 18 of them — every one a mission statement, a benefits list, a legal
notice or a heading — and keeps every block that states a requirement, including
the ones repeated verbatim across all 536 postings of the largest employer.

Both halves are derived from the postings themselves. A per-employer list of
paragraphs would rot the moment the employer edited their template.

The two thresholds ask different questions of different populations, which is
what lets one run recognise a template it only sees three postings of. Whether
an employer has a pattern at all is asked of everything known about them,
stored postings included. Whether this block is part of it is asked only of the
postings in hand, because a stored posting that was already stripped no longer
carries the block and would count as evidence against a template it is proof of.
"""

import logging
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from platform_db.models.catalog import normalize_company_name

from job_ingestion.schemas import NormalizedJob

logger = logging.getLogger(__name__)

# Below this an employer has no pattern, only a coincidence: two postings that
# share a paragraph say nothing about what the employer always writes.
MINIMUM_POSTINGS = 5

# A block has to be most of an employer's postings, not merely several of them.
MINIMUM_SHARE = 0.6

# A share needs something to be a share of. With one posting in hand every block
# in it is carried by all of them, and the rule collapses to "remove every
# paragraph that names the employer" — measured over this catalogue, that strips
# 1,384 blocks the whole-corpus rule keeps, including role descriptions. Two is
# where the error collapses: 87.
MINIMUM_POSTINGS_IN_HAND = 2

# What a block needs among the postings that still carry the employer's
# template, as opposed to among all of them. Higher, because that population is
# already narrowed to postings written from the template: what the template is,
# is what nearly all of them share. At 0.6 it also admits role bullets that
# happen to name the employer — measured, two of them on this catalogue.
NEARLY_ALL = 0.9

# Short enough to be ambiguous. `Init` is a name, `init` is a prefix of
# ordinary words, and the word boundary below is what keeps them apart; a
# two-letter marker has no such protection.
MINIMUM_MARKER_LENGTH = 4

# Dropped before the marker is chosen, because they name a company's legal form
# rather than the company.
LEGAL_FORMS = frozenset(
    {
        "ab",
        "ag",
        "aps",
        "as",
        "bv",
        "co",
        "corp",
        "corporation",
        "e",
        "gbr",
        "gmbh",
        "group",
        "holding",
        "inc",
        "kg",
        "limited",
        "llc",
        "lp",
        "ltd",
        "mbh",
        "nv",
        "ohg",
        "oy",
        "plc",
        "sa",
        "sas",
        "se",
        "spa",
        "srl",
        "ug",
        "v",
    }
)

NOT_ALPHANUMERIC = re.compile(r"[^0-9a-z]+")


@dataclass(frozen=True, slots=True)
class BoilerplatePolicy:
    """What makes a repeated block removable."""

    minimum_postings: int = MINIMUM_POSTINGS
    minimum_share: float = MINIMUM_SHARE
    minimum_postings_in_hand: int = MINIMUM_POSTINGS_IN_HAND

    def __post_init__(self) -> None:
        if self.minimum_postings < 2:
            raise ValueError("minimum_postings must be at least 2")
        if self.minimum_postings_in_hand < 2:
            raise ValueError("minimum_postings_in_hand must be at least 2")
        if not 0 < self.minimum_share <= 1:
            raise ValueError("minimum_share must be above zero and at most one")


@dataclass(frozen=True, slots=True)
class Removal:
    """How much was removed, so the change is measurable rather than trusted."""

    postings: int = 0
    blocks: int = 0
    characters: int = 0


def blocks(description: str) -> list[str]:
    """A description's paragraphs. Normalization already stores one per line."""
    return [line.strip() for line in description.splitlines() if line.strip()]


def folded(text: str) -> str:
    """What two spellings of the same block have in common.

    Padded with spaces so a name can be looked for as a whole word: without it
    an employer called `Init` would match every posting containing `initiative`.
    """
    return f" {NOT_ALPHANUMERIC.sub(' ', text.casefold()).strip()} "


def employer_marker(employer: str) -> str:
    """The word that means this employer and little else.

    The first name token that is neither a legal form nor too short to be
    distinctive — not every token, because an employer called `Quantum-Systems`
    would otherwise own every repeated sentence about distributed systems, and
    `Allica Bank` every sentence about banks. A name made entirely of short
    tokens falls back to the whole thing.
    """
    parts = [
        part for part in folded(normalize_company_name(employer)).split() if part not in LEGAL_FORMS
    ]
    for part in parts:
        if len(part) >= MINIMUM_MARKER_LENGTH:
            return part
    # No distinctive token, so no marker: `E.ON SE` would otherwise be `on`, and
    # a two-letter marker matched as a whole word is in most prose. An employer
    # nothing can name has nothing removed.
    return ""


def self_describing_blocks(
    employer: str,
    descriptions: Sequence[str],
    policy: BoilerplatePolicy,
    *,
    known_postings: int | None = None,
) -> frozenset[str]:
    """The folded blocks this employer repeats about itself.

    A block is removable when it appears in most of the given postings and names
    the employer. The second condition is what separates a blurb from a
    requirement every posting happens to share.

    `known_postings` is how many postings this employer has anywhere, which is
    what decides whether there is a pattern to find. It defaults to the ones
    given, so a caller with no catalogue behind it gets the plain rule.

    Two conditions, because they answer different questions. The catalogue says
    whether this employer has a template; the postings in hand say whether this
    block is part of it. The second needs enough postings to be a share of: with
    one, everything in it is carried by all of it.
    """
    if len(descriptions) < policy.minimum_postings_in_hand:
        return frozenset()
    if (known_postings if known_postings is not None else len(descriptions)) < (
        policy.minimum_postings
    ):
        return frozenset()

    marker = employer_marker(employer)
    if not marker:
        return frozenset()

    counts: Counter[str] = Counter()
    for description in descriptions:
        # Per posting rather than per occurrence, so a block written twice in
        # one posting does not count as two postings carrying it.
        counts.update({folded(block) for block in blocks(description)})

    threshold = policy.minimum_share * len(descriptions)
    return frozenset(
        block for block, seen in counts.items() if seen >= threshold and f" {marker} " in block
    )


def blocks_to_remove(
    descriptions_by_employer: Mapping[str, Sequence[str]],
    policy: BoilerplatePolicy | None = None,
) -> dict[str, frozenset[str]]:
    """The removable blocks of every employer in a catalogue.

    For a caller holding all of an employer's postings at once — a measurement
    or a backfill — rather than the handful a run fetched. There is no separate
    corpus to consult, because this is the corpus.
    """
    applied = policy if policy is not None else BoilerplatePolicy()
    return {
        employer: _stored_blocks(employer, descriptions, applied)
        for employer, descriptions in descriptions_by_employer.items()
    }


def _stored_blocks(
    employer: str,
    descriptions: Sequence[str],
    policy: BoilerplatePolicy,
) -> frozenset[str]:
    """The removable blocks of one employer's stored postings.

    Two ways in, because the population is not what it looks like. Ingestion
    strips as it writes, so by the time anyone reads a catalogue it is part
    cleaned, and a stripped posting carries none of the template: counting it as
    one that lacks a block makes it evidence against what it is proof of. On a
    catalogue six-tenths cleaned the plain share finds nothing at all and leaves
    the rest carrying the blurb forever, since an unchanged posting is never
    rewritten again.

    So a block is template either because most of the employer's postings carry
    it — the same rule a run applies, which keeps a clean catalogue's answer
    exactly as it was — or because nearly every posting that still carries any
    of the template carries it too. The second population is already narrowed to
    postings written from the template, which is why the bar there is
    near-unanimity: at the ordinary share it also admits role bullets that
    happen to name the employer, and this catalogue has two.
    """
    if len(descriptions) < policy.minimum_postings:
        return frozenset()

    marker = employer_marker(employer)
    if not marker:
        return frozenset()

    counts: Counter[str] = Counter()
    for description in descriptions:
        counts.update({folded(block) for block in blocks(description)})

    naming = {block: seen for block, seen in counts.items() if f" {marker} " in block}
    carrying = max(naming.values(), default=0)
    stated = policy.minimum_share * len(descriptions)
    # Two carriers is the same bar a run applies, and for the same reason: with
    # one, every block it holds is carried by all of them. On this catalogue the
    # only block admitted at exactly two is an `About ...` heading.
    nearly_all = NEARLY_ALL * carrying if carrying >= policy.minimum_postings_in_hand else None

    return frozenset(
        block
        for block, seen in naming.items()
        if seen >= stated or (nearly_all is not None and seen >= nearly_all)
    )


def without_blocks(description: str, removable: frozenset[str]) -> str:
    """The description with the named blocks gone.

    A description reduced to nothing keeps its original text. That should not
    happen — a posting made entirely of the employer's own blurb has no role in
    it — but an empty description is not storable, and dropping the posting over
    it would lose more than the boilerplate did.
    """
    kept = [block for block in blocks(description) if folded(block) not in removable]
    return "\n".join(kept) if kept else description


def strip_employer_boilerplate(
    jobs: Sequence[NormalizedJob],
    policy: BoilerplatePolicy | None = None,
    *,
    stored_postings: Mapping[str, int] | None = None,
) -> tuple[list[NormalizedJob], Removal]:
    """Drop each employer's self-description from its own postings.

    Employers are grouped across everything the run fetched, because a block
    repeats across an employer's postings and one posting cannot show that.

    `stored_postings` says how many postings the catalogue already holds for
    each employer, keyed by normalized name. It is what lets a source that
    delivers an employer a few postings at a time be stripped at all: those
    three postings are not a pattern, and three of a hundred are. Without it an
    employer is judged on the run alone, which is the honest reading of having
    too little to establish a pattern.
    """
    applied = policy if policy is not None else BoilerplatePolicy()
    known = stored_postings if stored_postings is not None else {}
    grouped: dict[str, list[NormalizedJob]] = defaultdict(list)
    for job in jobs:
        grouped[normalize_company_name(job.company.display_name)].append(job)

    removable = {
        employer: self_describing_blocks(
            employer,
            [job.description for job in employer_jobs],
            applied,
            # The larger of the two rather than their sum: a re-ingested
            # posting is in both populations and a new one is in neither, and
            # nothing here can tell which is which. Undercounting only ever
            # withholds stripping.
            known_postings=max(len(employer_jobs), known.get(employer, 0)),
        )
        for employer, employer_jobs in grouped.items()
    }

    stripped: list[NormalizedJob] = []
    postings = characters = removed_blocks = 0
    for job in jobs:
        drop = removable[normalize_company_name(job.company.display_name)]
        description = without_blocks(job.description, drop) if drop else job.description
        if description == job.description:
            stripped.append(job)
            continue
        postings += 1
        removed_blocks += len(blocks(job.description)) - len(blocks(description))
        characters += len(job.description) - len(description)
        stripped.append(job.model_copy(update={"description": description}))

    return stripped, Removal(postings=postings, blocks=removed_blocks, characters=characters)

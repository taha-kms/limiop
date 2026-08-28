"""Mapping of validated Arbeitnow records onto the canonical contract.

Pure and deterministic: the same record always produces the same canonical job,
and nothing here touches the network or the database.
"""

import re
from html.parser import HTMLParser

from platform_db.models.catalog import EmploymentType, WorkplaceType
from pydantic import ValidationError

from job_ingestion.arbeitnow.client import SOURCE_KEY
from job_ingestion.arbeitnow.records import ArbeitnowJobRecord, describe_failure
from job_ingestion.contracts import RawRecord
from job_ingestion.errors import RecordValidationError
from job_ingestion.schemas import NormalizedJob
from job_ingestion.vocabulary import (
    EMPLOYMENT_PRECEDENCE,
    WORKPLACE_PRECEDENCE,
    most_specific,
    stated_employments,
    stated_workplaces,
)

AGGREGATOR_FOOTER = re.compile(r"\s*Find (?:more [^\n]{1,40} )?Jobs in [^\n]{1,60} on Arbeitnow\Z")
"""The advertisement Arbeitnow appends to every posting it serves.

"Find more English Speaking Jobs in Germany on Arbeitnow" is the aggregator
talking about itself, not something the employer wrote, and it closes 488 of
the 491 Arbeitnow postings in the catalog. Left in, it makes English look like
the most demanded skill on the board: the word fires on 290 of 491 postings
with the footer and 112 without.

Anchored to the very end of the description rather than to a whole line. Five
postings end with the footer run onto the employer's own last sentence —
"E-Mail: Find Jobs in Germany on Arbeitnow" — because the text it followed
ended in an inline element that left no line break behind.
"""

IGNORED_HTML_CONTENT = frozenset({"script", "style"})
HTML_LINE_BREAKS = frozenset(
    {
        "br",
        "p",
        "div",
        "li",
        "ul",
        "ol",
        "tr",
        "table",
        "section",
        "article",
        "header",
        "footer",
        "blockquote",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    }
)


# A pass that changes anything strictly shortens the text: entities decode to
# fewer characters and tags are removed outright. Flattening therefore settles
# on its own, and this bound only exists so an unforeseen pass that grows the
# text cannot loop forever.
MAX_FLATTENING_PASSES = 10


class PlainTextExtractor(HTMLParser):
    """Collects readable text from untrusted markup.

    `HTMLParser` never executes what it reads, and script and style bodies are
    dropped so their contents cannot end up in a stored description.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self.ignoring = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in IGNORED_HTML_CONTENT:
            self.ignoring += 1
        if tag in HTML_LINE_BREAKS:
            self.chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in IGNORED_HTML_CONTENT and self.ignoring:
            self.ignoring -= 1
        if tag in HTML_LINE_BREAKS:
            self.chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.ignoring:
            self.chunks.append(data)


def flatten_once(markup: str) -> str:
    """Strip one layer of markup, keeping paragraph breaks."""
    extractor = PlainTextExtractor()
    extractor.feed(markup)
    extractor.close()
    lines = (" ".join(line.split()) for line in "".join(extractor.chunks).splitlines())
    return "\n".join(line for line in lines if line)


def to_plain_text(markup: str) -> str:
    """Turn provider markup into plain text, however it was encoded.

    One pass is not enough. Some postings arrive with their markup
    entity-escaped, and the parser sees no tags in `&lt;p&gt;text&lt;/p&gt;` at
    all: it is character data, so the entities are decoded and the pass returns
    `<p>text</p>`. Stripping nothing while producing tags is worse than doing
    nothing, because the script and style dropping never runs on markup the
    parser never recognised.

    So flattening repeats until its own output stops changing. Each changing
    pass strictly shortens the text, so this settles on its own; the bound is
    a guard rather than the mechanism.
    """
    text = markup
    for _ in range(MAX_FLATTENING_PASSES):
        flattened = flatten_once(text)
        if flattened == text:
            return text
        text = flattened
    return text


def without_aggregator_footer(text: str) -> str:
    """Drop Arbeitnow's own trailing advertisement, if it is there.

    Only a match that runs to the end of the description is removed, so a
    posting that discusses finding jobs anywhere else keeps its text.
    """
    return AGGREGATOR_FOOTER.sub("", text)


def to_employment_type(job_types: tuple[str, ...]) -> EmploymentType:
    """Pick the most specific employment type the provider named."""
    return most_specific(
        stated_employments(*job_types),
        EMPLOYMENT_PRECEDENCE,
        EmploymentType.UNSPECIFIED,
    )


def to_workplace_type(
    remote: bool,
    location: str | None,
    tags: tuple[str, ...],
) -> WorkplaceType:
    """Read the arrangement from every field that states one.

    The `remote` flag is the weakest signal the provider offers, not the only
    one: it is false on postings whose own location reads `Germany Remote` or
    `Berlin, Hybrid`. Taking it as authoritative left nine in ten jobs
    unspecified.

    Reading those words is extraction, not invention. The provider stated the
    arrangement, just not in the field built for it. What would be invention is
    concluding `onsite` from silence, which the shared vocabulary refuses.

    Titles are deliberately not read. `Remote Sensing Engineer` is a real job
    title and a real false positive; location and tag fields carry no
    equivalent risk.
    """
    stated = {WorkplaceType.REMOTE} if remote else set()
    stated |= stated_workplaces(location, *tags)
    return most_specific(stated, WORKPLACE_PRECEDENCE, WorkplaceType.UNSPECIFIED)


class ArbeitnowNormalizer:
    """Maps one validated Arbeitnow record onto the canonical contract."""

    def normalize(self, record: ArbeitnowJobRecord, raw: RawRecord) -> NormalizedJob:
        location = record.location or None
        try:
            return NormalizedJob.model_validate(
                {
                    "company": {"display_name": record.company_name},
                    "title": record.title,
                    "description": without_aggregator_footer(to_plain_text(record.description)),
                    "location": location,
                    "workplace_type": to_workplace_type(
                        record.remote, record.location, record.tags
                    ),
                    "employment_type": to_employment_type(record.job_types),
                    "application_url": str(record.url),
                    "published_at": record.created_at,
                    "provenance": {
                        "source_key": SOURCE_KEY,
                        "source_job_id": record.slug,
                        "source_url": str(record.url),
                        "raw_payload": dict(raw),
                    },
                }
            )
        except ValidationError as error:
            raise RecordValidationError(
                SOURCE_KEY,
                describe_failure(error),
                source_job_id=record.slug,
            ) from error

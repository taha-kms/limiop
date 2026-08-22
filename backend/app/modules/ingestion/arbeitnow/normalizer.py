"""Mapping of validated Arbeitnow records onto the canonical contract.

Pure and deterministic: the same record always produces the same canonical job,
and nothing here touches the network or the database.
"""

import re
from html.parser import HTMLParser

from pydantic import ValidationError

from app.modules.ingestion.arbeitnow.client import SOURCE_KEY
from app.modules.ingestion.arbeitnow.records import ArbeitnowJobRecord, describe_failure
from app.modules.ingestion.contracts import RawRecord
from app.modules.ingestion.errors import RecordValidationError
from app.modules.jobs.domain import EmploymentType, WorkplaceType
from app.modules.jobs.schemas import NormalizedJob

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

EMPLOYMENT_BY_TOKEN = {
    "full time": EmploymentType.FULL_TIME,
    "fulltime": EmploymentType.FULL_TIME,
    "part time": EmploymentType.PART_TIME,
    "parttime": EmploymentType.PART_TIME,
    "contract": EmploymentType.CONTRACT,
    "contractor": EmploymentType.CONTRACT,
    "freelance": EmploymentType.CONTRACT,
    "internship": EmploymentType.INTERNSHIP,
    "intern": EmploymentType.INTERNSHIP,
    "temporary": EmploymentType.TEMPORARY,
    "temp": EmploymentType.TEMPORARY,
}

# A record may carry several job types. The most specific one wins so that an
# internship advertised as part time is not filed as ordinary part-time work.
EMPLOYMENT_PRECEDENCE = (
    EmploymentType.INTERNSHIP,
    EmploymentType.TEMPORARY,
    EmploymentType.CONTRACT,
    EmploymentType.PART_TIME,
    EmploymentType.FULL_TIME,
)


# A pass that changes anything strictly shortens the text: entities decode to
# fewer characters and tags are removed outright. Flattening therefore settles
# on its own, and this bound only exists so an unforeseen pass that grows the
# text cannot loop forever.
MAX_FLATTENING_PASSES = 10


# Phrases a provider uses to name an arrangement, in the two languages this
# board publishes in. Keys are already tokenized, so a phrase written with a
# hyphen, an underscore, or extra spacing resolves to the same entry.
WORKPLACE_BY_PHRASE = {
    "remote": WorkplaceType.REMOTE,
    "fully remote": WorkplaceType.REMOTE,
    "home office": WorkplaceType.REMOTE,
    "homeoffice": WorkplaceType.REMOTE,
    "telearbeit": WorkplaceType.REMOTE,
    "hybrid": WorkplaceType.HYBRID,
    "teilweise remote": WorkplaceType.HYBRID,
    "on site": WorkplaceType.ONSITE,
    "onsite": WorkplaceType.ONSITE,
    "vor ort": WorkplaceType.ONSITE,
    "präsenz": WorkplaceType.ONSITE,
}

# Longest first, so `teilweise remote` is read as hybrid rather than matching
# `remote` inside it. Word boundaries stop a phrase being found inside an
# unrelated word.
WORKPLACE_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(
        re.escape(phrase).replace(r"\ ", r"[\s_-]+")
        for phrase in sorted(WORKPLACE_BY_PHRASE, key=len, reverse=True)
    )
    + r")\b",
    re.IGNORECASE,
)

# Hybrid outranks remote because it is the more specific claim: it asserts both
# arrangements, so a posting described as each is hybrid.
WORKPLACE_PRECEDENCE = (
    WorkplaceType.HYBRID,
    WorkplaceType.REMOTE,
    WorkplaceType.ONSITE,
)


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


def to_token(value: str) -> str:
    """Reduce a provider label to a comparable token."""
    return " ".join(value.replace("_", " ").replace("-", " ").casefold().split())


def to_employment_type(job_types: tuple[str, ...]) -> EmploymentType:
    """Pick the most specific employment type the provider named."""
    matched = {
        EMPLOYMENT_BY_TOKEN[token]
        for value in job_types
        if (token := to_token(value)) in EMPLOYMENT_BY_TOKEN
    }
    for candidate in EMPLOYMENT_PRECEDENCE:
        if candidate in matched:
            return candidate
    return EmploymentType.UNSPECIFIED


def stated_workplaces(text: str) -> set[WorkplaceType]:
    """Every arrangement a piece of provider text names outright."""
    return {WORKPLACE_BY_PHRASE[to_token(match)] for match in WORKPLACE_PATTERN.findall(text)}


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
    concluding `onsite` from silence, so `onsite` is reachable only from words
    that say it. Nothing observed uses those words, and a job that never becomes
    onsite is the right outcome rather than a gap.

    The most specific arrangement wins when fields disagree, because a posting
    tagged remote whose location says hybrid has an on-site component and
    `hybrid` is the claim that survives both.
    """
    stated = {WorkplaceType.REMOTE} if remote else set()
    stated |= stated_workplaces(location or "")
    for tag in tags:
        stated |= stated_workplaces(tag)

    for candidate in WORKPLACE_PRECEDENCE:
        if candidate in stated:
            return candidate
    return WorkplaceType.UNSPECIFIED


class ArbeitnowNormalizer:
    """Maps one validated Arbeitnow record onto the canonical contract."""

    def normalize(self, record: ArbeitnowJobRecord, raw: RawRecord) -> NormalizedJob:
        location = record.location or None
        try:
            return NormalizedJob.model_validate(
                {
                    "company": {"display_name": record.company_name},
                    "title": record.title,
                    "description": to_plain_text(record.description),
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

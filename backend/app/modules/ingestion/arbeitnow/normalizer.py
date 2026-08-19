"""Mapping of validated Arbeitnow records onto the canonical contract.

Pure and deterministic: the same record always produces the same canonical job,
and nothing here touches the network or the database.
"""

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


def to_plain_text(markup: str) -> str:
    """Turn provider markup into plain text, keeping paragraph breaks."""
    extractor = PlainTextExtractor()
    extractor.feed(markup)
    extractor.close()
    lines = (" ".join(line.split()) for line in "".join(extractor.chunks).splitlines())
    return "\n".join(line for line in lines if line)


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


def to_workplace_type(remote: bool) -> WorkplaceType:
    """Map the provider's only workplace signal.

    Arbeitnow flags remote work and says nothing otherwise, so an unflagged job
    is `unspecified` rather than `onsite`. Claiming onsite would invent a fact.
    """
    return WorkplaceType.REMOTE if remote else WorkplaceType.UNSPECIFIED


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
                    "workplace_type": to_workplace_type(record.remote),
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

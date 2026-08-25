"""Validation of untrusted Arbeitnow records.

These schemas describe what Arbeitnow sends, not what SkillSync stores. They
stay separate from the canonical contract so a provider quirk can never widen
the shared job model. Deciding what a value means is normalization's job; this
stage only decides whether the record is usable at all.
"""

from typing import Annotated

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    HttpUrl,
    StringConstraints,
    ValidationError,
)

from job_ingestion.arbeitnow.client import SOURCE_KEY
from job_ingestion.contracts import RawRecord
from job_ingestion.errors import RecordValidationError

Required = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Trimmed = Annotated[str, StringConstraints(strip_whitespace=True)]


class ArbeitnowJobRecord(BaseModel):
    """One Arbeitnow job posting, after validation.

    Unknown fields are ignored rather than rejected: Arbeitnow may add fields at
    any time, and that must not stop ingestion.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    slug: Required
    title: Required
    company_name: Required
    description: Required
    url: HttpUrl
    remote: bool = False
    location: Trimmed | None = None
    tags: tuple[str, ...] = ()
    job_types: tuple[str, ...] = ()
    created_at: AwareDatetime | None = None


def describe_failure(error: ValidationError) -> str:
    """Summarize why a record was rejected, without repeating provider data."""
    problems = [
        f"{'.'.join(str(part) for part in detail['loc']) or 'record'}: {detail['msg']}"
        for detail in error.errors(include_url=False, include_input=False)
    ]
    return "; ".join(problems)


def readable_slug(record: RawRecord) -> str | None:
    """Return the record's own identifier when it is usable for reporting."""
    slug = record.get("slug")
    if isinstance(slug, str) and slug.strip():
        return slug.strip()
    return None


class ArbeitnowValidator:
    """Turns one untrusted Arbeitnow record into a typed provider record."""

    def validate(self, record: RawRecord) -> ArbeitnowJobRecord:
        try:
            return ArbeitnowJobRecord.model_validate(record)
        except ValidationError as error:
            raise RecordValidationError(
                SOURCE_KEY,
                describe_failure(error),
                source_job_id=readable_slug(record),
            ) from error

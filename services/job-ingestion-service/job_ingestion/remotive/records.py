"""Validation of untrusted Remotive records.

These schemas describe what Remotive sends, not what SkillSync stores. They
stay separate from the canonical contract so a provider quirk can never widen
the shared job model. Deciding what a value means is normalization's job; this
stage only decides whether the record is usable at all.
"""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    HttpUrl,
    StringConstraints,
    ValidationError,
    field_validator,
)

from job_ingestion.contracts import RawRecord
from job_ingestion.errors import RecordValidationError
from job_ingestion.remotive.client import SOURCE_KEY

Required = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class RemotiveJobRecord(BaseModel):
    """One Remotive job posting, after validation.

    Unknown fields are ignored rather than rejected: Remotive may add fields at
    any time, and that must not stop ingestion. `id` is a bare JSON number in
    every posting the live feed returns, so it is kept as `int` here and
    stringified only at the provenance boundary, where the canonical contract
    stores an identifier as text.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    id: int
    title: Required
    company_name: Required
    description: Required
    url: HttpUrl
    job_type: str = ""
    candidate_required_location: str = ""
    publication_date: datetime | None = None

    @field_validator("publication_date", mode="after")
    @classmethod
    def _assume_utc(cls, value: datetime | None) -> datetime | None:
        """Treat a naive publication date as UTC.

        Remotive's `publication_date` carries no offset -- `2026-09-11T20:16:48`
        rather than `...+00:00` -- and the API documentation states the feed
        publishes in UTC. A naive value here is that omission, not a provider
        mistake, so it is stamped UTC rather than refused: refusing it would
        discard a real posting over a formatting choice the provider made
        consistently.
        """
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


def describe_failure(error: ValidationError) -> str:
    """Summarize why a record was rejected, without repeating provider data."""
    problems = [
        f"{'.'.join(str(part) for part in detail['loc']) or 'record'}: {detail['msg']}"
        for detail in error.errors(include_url=False, include_input=False)
    ]
    return "; ".join(problems)


def readable_identifier(record: RawRecord) -> str | None:
    """Return the record's own identifier when it is usable for reporting."""
    identifier = record.get("id")
    if isinstance(identifier, int) and not isinstance(identifier, bool):
        return str(identifier)
    return None


class RemotiveValidator:
    """Turns one untrusted Remotive record into a typed provider record."""

    def validate(self, record: RawRecord) -> RemotiveJobRecord:
        try:
            return RemotiveJobRecord.model_validate(record)
        except ValidationError as error:
            raise RecordValidationError(
                SOURCE_KEY,
                describe_failure(error),
                source_job_id=readable_identifier(record),
            ) from error

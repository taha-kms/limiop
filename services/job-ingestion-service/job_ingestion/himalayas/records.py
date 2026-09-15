"""Validation of untrusted Himalayas records.

These schemas describe what Himalayas sends, not what SkillSync stores. They
stay separate from the canonical contract so a provider quirk can never widen
the shared job model. Deciding what a value means is normalization's job; this
stage only decides whether the record is usable at all.
"""

from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    HttpUrl,
    StringConstraints,
    ValidationError,
)

from job_ingestion.contracts import RawRecord
from job_ingestion.errors import RecordValidationError
from job_ingestion.himalayas.client import SOURCE_KEY

Required = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _coerce_location_restrictions(value: object) -> object:
    """Accept whatever shape the feed happens to send for this field.

    Most postings carry a list of country or region names. A blank feed sends
    `null` for a posting with no restriction on record, and a single
    restriction has been observed collapsed to a bare string rather than a
    one-element list. Normalized to a single return so every path leaves this
    function through the same statement.
    """
    if value is None:
        value = ()
    elif isinstance(value, str):
        value = (value,)
    return value


def _coerce_epoch_seconds(value: object) -> object:
    """Accept an epoch-second integer, or the same value sent as a string."""
    if isinstance(value, str):
        stripped = value.strip()
        try:
            return int(stripped)
        except ValueError:
            raise ValueError("must be an integer number of seconds") from None
    return value


def _reject_negative_epoch(value: int | None) -> int | None:
    if value is not None and value < 0:
        raise ValueError("must not be negative")
    return value


LocationRestrictions = Annotated[tuple[str, ...], BeforeValidator(_coerce_location_restrictions)]
EpochSeconds = Annotated[
    int | None,
    BeforeValidator(_coerce_epoch_seconds),
    AfterValidator(_reject_negative_epoch),
]


class HimalayasJobRecord(BaseModel):
    """One Himalayas job posting, after validation.

    Unknown fields are ignored rather than rejected: Himalayas may add fields
    at any time, and that must not stop ingestion.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    guid: HttpUrl
    title: Required
    companyName: Required
    description: Required
    applicationLink: HttpUrl
    employmentType: str = ""
    locationRestrictions: LocationRestrictions = ()
    pubDate: EpochSeconds = None
    expiryDate: EpochSeconds = None


def describe_failure(error: ValidationError) -> str:
    """Summarize why a record was rejected, without repeating provider data."""
    problems = [
        f"{'.'.join(str(part) for part in detail['loc']) or 'record'}: {detail['msg']}"
        for detail in error.errors(include_url=False, include_input=False)
    ]
    return "; ".join(problems)


def readable_identifier(record: RawRecord) -> str | None:
    """Return the record's own identifier when it is usable for reporting."""
    guid = record.get("guid")
    if isinstance(guid, str) and guid.strip():
        return guid.strip()
    return None


class HimalayasValidator:
    """Turns one untrusted Himalayas record into a typed provider record."""

    def validate(self, record: RawRecord) -> HimalayasJobRecord:
        try:
            return HimalayasJobRecord.model_validate(record)
        except ValidationError as error:
            raise RecordValidationError(
                SOURCE_KEY,
                describe_failure(error),
                source_job_id=readable_identifier(record),
            ) from error

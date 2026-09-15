"""Validation of untrusted Jobicy records.

These schemas describe what Jobicy sends, not what SkillSync stores. They stay
separate from the canonical contract so a provider quirk can never widen the
shared job model. Deciding what a value means is normalization's job; this
stage only decides whether the record is usable at all.
"""

from typing import Annotated, Any

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    HttpUrl,
    StringConstraints,
    ValidationError,
)

from job_ingestion.contracts import RawRecord
from job_ingestion.errors import RecordValidationError
from job_ingestion.jobicy.client import SOURCE_KEY

Required = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Trimmed = Annotated[str, StringConstraints(strip_whitespace=True)]


def coerce_identifier(value: Any) -> Any:
    """Accept the feed's numeric `id` as well as a string one.

    Jobicy sends `id` as a JSON number, not the string the documentation
    implies. Everything downstream (provenance, failure reporting) treats an
    identifier as text, so the coercion happens once, here, rather than at
    every call site.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


def coerce_job_type(value: Any) -> Any:
    """Accept a list of job types, a single one, or none at all.

    Jobicy usually sends `jobType` as a list, but a single string and a null
    both appear in the wild. Reducing every shape to a list here keeps the
    schema's own type a plain tuple.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return value


Identifier = Annotated[Required, BeforeValidator(coerce_identifier)]
JobTypes = Annotated[tuple[str, ...], BeforeValidator(coerce_job_type)]


class JobicyJobRecord(BaseModel):
    """One Jobicy job posting, after validation.

    Unknown fields are ignored rather than rejected: Jobicy may add fields at
    any time, and that must not stop ingestion.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    id: Identifier
    jobTitle: Required
    companyName: Required
    jobDescription: Required
    url: HttpUrl
    jobGeo: Trimmed = ""
    jobType: JobTypes = ()
    jobLevel: Trimmed = ""
    pubDate: AwareDatetime | None = None


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
    if isinstance(identifier, str) and identifier.strip():
        return identifier.strip()
    if isinstance(identifier, int) and not isinstance(identifier, bool):
        return str(identifier)
    return None


class JobicyValidator:
    """Turns one untrusted Jobicy record into a typed provider record."""

    def validate(self, record: RawRecord) -> JobicyJobRecord:
        try:
            return JobicyJobRecord.model_validate(record)
        except ValidationError as error:
            raise RecordValidationError(
                SOURCE_KEY,
                describe_failure(error),
                source_job_id=readable_identifier(record),
            ) from error

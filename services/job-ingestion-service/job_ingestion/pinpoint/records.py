"""Validation of untrusted Pinpoint records.

These schemas describe what a Pinpoint board sends, not what SkillSync
stores. A provider quirk can never widen the shared job model, and deciding
what a value means is normalization's job; this stage only decides whether the
record is usable at all.
"""

from typing import Annotated

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    ValidationError,
    field_validator,
)

from job_ingestion.contracts import RawRecord
from job_ingestion.errors import RecordValidationError
from job_ingestion.pinpoint.source import SOURCE_KEY

Required = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def blank_for_null(value: object) -> object:
    """A field the board has no value for arrives as null, not as an absent key."""
    return "" if value is None else value


# An optional string: the board may omit it, send it empty, or send null, and
# every one of those means the posting says nothing here. The required fields
# above stay strict; a null title or description is still a refused record.
Nullable = Annotated[str, BeforeValidator(blank_for_null)]


class PinpointLocation(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    name: Nullable = ""
    city: Nullable = ""


class PinpointJobRecord(BaseModel):
    """One Pinpoint posting, after validation.

    Unknown fields are ignored rather than rejected: a board may gain fields
    at any time, and that must not stop ingestion. `description` is required
    because there is no detail request to fall back on for this provider: one
    request answers the whole posting, so a record still missing it is simply
    a record the board never carried a description for.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    board: Required
    id: Required
    title: Required
    description: Required
    key_responsibilities: Nullable = ""
    skills_knowledge_expertise: Nullable = ""
    url: HttpUrl
    location: PinpointLocation = Field(default_factory=PinpointLocation)
    workplace_type: Nullable = ""
    workplace_type_text: Nullable = ""
    employment_type: Nullable = ""
    employment_type_text: Nullable = ""
    deadline_at: AwareDatetime | None = None

    @field_validator("location", mode="before")
    @classmethod
    def tolerate_a_missing_location(cls, value: object) -> object:
        """A posting with no location on record sends null rather than an object."""
        return {} if value is None else value


def describe_failure(error: ValidationError) -> str:
    """Summarize why a record was rejected, without repeating provider data."""
    problems = [
        f"{'.'.join(str(part) for part in detail['loc']) or 'record'}: {detail['msg']}"
        for detail in error.errors(include_url=False, include_input=False)
    ]
    return "; ".join(problems)


def readable_identifier(record: RawRecord) -> str | None:
    """Return the record's own identifier when it is usable for reporting."""
    board = record.get("board")
    identifier = record.get("id")
    if (
        isinstance(board, str)
        and board.strip()
        and isinstance(identifier, str)
        and identifier.strip()
    ):
        return f"{board.strip()}:{identifier.strip()}"
    return None


class PinpointValidator:
    """Turns one untrusted Pinpoint record into a typed provider record."""

    def validate(self, record: RawRecord) -> PinpointJobRecord:
        try:
            return PinpointJobRecord.model_validate(record)
        except ValidationError as error:
            raise RecordValidationError(
                SOURCE_KEY,
                describe_failure(error),
                source_job_id=readable_identifier(record),
            ) from error

"""Validation of untrusted Greenhouse records.

These schemas describe what a Greenhouse board sends, not what SkillSync
stores. A provider quirk can never widen the shared job model, and deciding
what a value means is normalization's job; this stage only decides whether the
record is usable at all.
"""

from typing import Annotated, Any

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    ValidationError,
    field_validator,
)

from app.modules.ingestion.contracts import RawRecord
from app.modules.ingestion.errors import RecordValidationError
from app.modules.ingestion.greenhouse.client import SOURCE_KEY

Required = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class GreenhouseMetadatum(BaseModel):
    """One employer-defined field on a posting.

    Employers choose these names and values themselves, so nothing here is a
    controlled vocabulary. Both are kept as text and interpreted later, or not.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    name: str = ""
    value: Any = None


class GreenhouseLocation(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    name: str = ""


class GreenhouseJobRecord(BaseModel):
    """One Greenhouse posting, after validation.

    Unknown fields are ignored rather than rejected: a board may gain fields at
    any time, and that must not stop ingestion.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    board: Required
    id: int
    title: Required
    company_name: Required
    content: Required
    absolute_url: HttpUrl
    location: GreenhouseLocation = Field(default_factory=GreenhouseLocation)
    metadata: tuple[GreenhouseMetadatum, ...] = ()
    first_published: AwareDatetime | None = None
    updated_at: AwareDatetime | None = None
    application_deadline: AwareDatetime | None = None

    @field_validator("metadata", mode="before")
    @classmethod
    def tolerate_a_missing_metadata_list(cls, value: object) -> object:
        """A board with no employer-defined fields sends null rather than an empty list."""
        return () if value is None else value

    def stated(self, *names: str) -> tuple[str, ...]:
        """Values of the employer-defined fields matching any of these names.

        Matched loosely, because the names are the employer's own words. A
        board calls the same thing `Location Type`, `Workplace`, or nothing at
        all.
        """
        wanted = {name.casefold() for name in names}
        return tuple(
            str(item.value)
            for item in self.metadata
            if item.name.strip().casefold() in wanted and item.value is not None
        )


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
    if isinstance(identifier, int) and isinstance(board, str) and board.strip():
        return f"{board.strip()}:{identifier}"
    return None


class GreenhouseValidator:
    """Turns one untrusted Greenhouse record into a typed provider record."""

    def validate(self, record: RawRecord) -> GreenhouseJobRecord:
        try:
            return GreenhouseJobRecord.model_validate(record)
        except ValidationError as error:
            raise RecordValidationError(
                SOURCE_KEY,
                describe_failure(error),
                source_job_id=readable_identifier(record),
            ) from error

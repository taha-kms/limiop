"""Validation of untrusted Polymer records.

These schemas describe what a Polymer board sends, not what SkillSync
stores. A provider quirk can never widen the shared job model, and deciding
what a value means is normalization's job; this stage only decides whether the
record is usable at all.
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

from job_ingestion.contracts import RawRecord
from job_ingestion.errors import RecordValidationError
from job_ingestion.polymer.source import SOURCE_KEY

Required = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class PolymerJobRecord(BaseModel):
    """One Polymer posting, after validation.

    Unknown fields are ignored rather than rejected: a board may gain fields at
    any time, and that must not stop ingestion. `description` is required
    because the listing never carries one; a record still missing it after
    hydration is what a failed detail fetch already produces, so refusing it
    here reaches the same conclusion by the same route.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    board: Required
    id: int
    title: Required
    organization_name: Required
    description: Required
    job_post_url: HttpUrl
    display_location: str = ""
    remoteness_pretty: str = ""
    kind_pretty: str = ""
    published_at: AwareDatetime | None = None
    archived_at: AwareDatetime | None = None


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


class PolymerValidator:
    """Turns one untrusted Polymer record into a typed provider record."""

    def validate(self, record: RawRecord) -> PolymerJobRecord:
        try:
            return PolymerJobRecord.model_validate(record)
        except ValidationError as error:
            raise RecordValidationError(
                SOURCE_KEY,
                describe_failure(error),
                source_job_id=readable_identifier(record),
            ) from error

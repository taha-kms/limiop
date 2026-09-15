"""Validation of untrusted Adzuna records.

These schemas describe what Adzuna sends, not what SkillSync stores. They stay
separate from the canonical contract so a provider quirk can never widen the
shared job model. Deciding what a value means is normalization's job; this
stage only decides whether the record is usable at all.

A result is identified by `id` only within the country it was searched in, so
the client stamps `country` on every record it yields and the two together
are the record's identity here.
"""

from typing import Annotated, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    HttpUrl,
    StringConstraints,
    ValidationError,
    model_validator,
)

from job_ingestion.adzuna.source import SOURCE_KEY
from job_ingestion.contracts import RawRecord
from job_ingestion.errors import RecordValidationError

Required = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Trimmed = Annotated[str, StringConstraints(strip_whitespace=True)]


def _coerce_identifier(value: object) -> object:
    """Accept an id sent as an integer as the string it is documented to be.

    Only an integer is coerced: `str(None)` would turn a missing id into the
    usable-looking "None", and a bool is not an identifier.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


Identifier = Annotated[Required, BeforeValidator(_coerce_identifier)]


def provenance_id(country: str, identifier: str) -> str:
    """The identity a record has across the whole source, not just its country."""
    return f"{country}:{identifier}"


class AdzunaCompany(BaseModel):
    """The `company` object of a result."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    display_name: Trimmed = ""


class AdzunaLocation(BaseModel):
    """The `location` object of a result: a display name and its containing areas."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    display_name: Trimmed = ""
    area: tuple[str, ...] = ()


class AdzunaJobRecord(BaseModel):
    """One Adzuna search result, after validation.

    Unknown fields are ignored rather than rejected: Adzuna may add fields at
    any time, and that must not stop ingestion. `description` is the excerpt
    the API serves, never the posting; the normalizer says so in provenance.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    id: Identifier
    country: Required
    title: Required
    description: Required
    redirect_url: HttpUrl
    company: AdzunaCompany = AdzunaCompany()
    location: AdzunaLocation = AdzunaLocation()
    contract_type: str = ""
    contract_time: str = ""
    created: AwareDatetime | None = None

    @model_validator(mode="after")
    def require_an_employer(self) -> Self:
        """Refuse a result that names no employer.

        The catalogue files every posting under a company, and Adzuna does
        send results whose `company` is missing or blank. Nothing sensible can
        stand in for the employer, so the record is unusable rather than
        stored under a placeholder.
        """
        if not self.company.display_name:
            raise ValueError("company.display_name must name an employer")
        return self


def describe_failure(error: ValidationError) -> str:
    """Summarize why a record was rejected, without repeating provider data."""
    problems = [
        f"{'.'.join(str(part) for part in detail['loc']) or 'record'}: {detail['msg']}"
        for detail in error.errors(include_url=False, include_input=False)
    ]
    return "; ".join(problems)


def readable_identifier(record: RawRecord) -> str | None:
    """The record's identity for reporting, as far as its parts are usable.

    Country and id when the record has been stamped, the bare id when it has
    not, and nothing when the id itself is not a usable string.
    """
    identifier = _coerce_identifier(record.get("id"))
    if not isinstance(identifier, str) or not identifier.strip():
        return None
    country = record.get("country")
    if isinstance(country, str) and country.strip():
        return provenance_id(country.strip(), identifier.strip())
    return identifier.strip()


class AdzunaValidator:
    """Turns one untrusted Adzuna result into a typed provider record."""

    def validate(self, record: RawRecord) -> AdzunaJobRecord:
        try:
            return AdzunaJobRecord.model_validate(record)
        except ValidationError as error:
            raise RecordValidationError(
                SOURCE_KEY,
                describe_failure(error),
                source_job_id=readable_identifier(record),
            ) from error

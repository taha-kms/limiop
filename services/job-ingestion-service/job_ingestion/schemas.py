"""Validation schemas for normalized job postings."""

from typing import Annotated, Any, Self

from platform_db.models.catalog import EmploymentType, WorkplaceType
from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    HttpUrl,
    StringConstraints,
    model_validator,
)

MAX_SOURCE_KEY_LENGTH = 100
MAX_NAME_LENGTH = 255
MAX_URL_LENGTH = 2048


def bound_url_length(value: HttpUrl) -> HttpUrl:
    """Reject URLs that a persisted column cannot hold."""
    if len(str(value)) > MAX_URL_LENGTH:
        raise ValueError(f"URL must not exceed {MAX_URL_LENGTH} characters")
    return value


Url = Annotated[HttpUrl, AfterValidator(bound_url_length)]
Name = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_NAME_LENGTH),
]
SourceKey = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_SOURCE_KEY_LENGTH),
]
Prose = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class NormalizedCompany(BaseModel):
    """Employer identity carried by a normalized job."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: Name
    website_url: Url | None = None


class NormalizedProvenance(BaseModel):
    """The external record a normalized job was derived from."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_key: SourceKey
    source_job_id: Name
    source_url: Url
    raw_payload: dict[str, Any] | None = None


class NormalizedJob(BaseModel):
    """One provider record expressed in the canonical vocabulary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    company: NormalizedCompany
    title: Name
    description: Prose
    location: Name | None = None
    workplace_type: WorkplaceType = WorkplaceType.UNSPECIFIED
    employment_type: EmploymentType = EmploymentType.UNSPECIFIED
    application_url: Url
    published_at: AwareDatetime | None = None
    expires_at: AwareDatetime | None = None
    provenance: NormalizedProvenance

    @model_validator(mode="after")
    def reject_expiry_before_publication(self) -> Self:
        published_at = self.published_at
        expires_at = self.expires_at
        if published_at is not None and expires_at is not None and expires_at < published_at:
            raise ValueError("expires_at must not precede published_at")
        return self

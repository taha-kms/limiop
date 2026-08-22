"""Validation schemas for the job catalog."""

from datetime import datetime
from typing import Annotated, Any, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    model_validator,
)

from app.modules.jobs.domain import EmploymentType, JobStatus, WorkplaceType
from app.modules.jobs.queries import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    JobFilters,
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
    """One provider record expressed in the canonical vocabulary.

    This is the only shape a provider normalizer may produce and the only shape
    persistence accepts. Provenance is nested rather than passed alongside so a
    job cannot be normalized without recording where it came from.
    """

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


class CompanyRead(BaseModel):
    """Employer identity as served to callers."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str
    website_url: HttpUrl | None


class ProvenanceRead(BaseModel):
    """Source attribution safe to serve.

    Raw payloads are untrusted provider data and have no field here, so no
    caller can expose them by forgetting to exclude them.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    source_job_id: str
    source_url: HttpUrl
    first_seen_at: datetime
    last_seen_at: datetime


class JobRead(BaseModel):
    """A canonical job as served to callers."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company: CompanyRead
    title: str
    description: str
    location: str | None
    workplace_type: WorkplaceType
    employment_type: EmploymentType
    application_url: HttpUrl
    published_at: datetime | None
    expires_at: datetime | None
    status: JobStatus
    created_at: datetime
    updated_at: datetime


MAX_CURSOR_LENGTH = 512
MAX_QUERY_LENGTH = 200

SearchTerm = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUERY_LENGTH),
]


class JobSummary(BaseModel):
    """A job as it appears in a listing.

    Deliberately narrower than `JobRead`: no description. A batch of twenty full
    postings is most of a megabyte of prose nobody reads while scrolling, and
    the detail endpoint already serves it to the one job a reader opens.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company: CompanyRead
    title: str
    location: str | None
    workplace_type: WorkplaceType
    employment_type: EmploymentType
    application_url: HttpUrl
    published_at: datetime | None


class JobListQuery(BaseModel):
    """Everything a caller may ask of the listing.

    Unknown parameters are refused rather than ignored. A misspelled filter that
    is silently dropped returns the whole catalog and looks like a filter that
    matched everything, which is the kind of wrong answer nobody reports.
    """

    model_config = ConfigDict(extra="forbid")

    cursor: str | None = Field(
        default=None,
        max_length=MAX_CURSOR_LENGTH,
        description="Opaque position token from a previous response. Do not construct one.",
    )
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    company_id: UUID | None = None
    location: SearchTerm | None = None
    workplace_type: list[WorkplaceType] = Field(default_factory=list)
    employment_type: list[EmploymentType] = Field(default_factory=list)
    q: SearchTerm | None = Field(default=None, description="Free-text search over job titles.")

    def to_filters(self) -> JobFilters:
        return JobFilters(
            company_id=self.company_id,
            location=self.location,
            workplace_types=frozenset(self.workplace_type),
            employment_types=frozenset(self.employment_type),
            title_query=self.q,
        )


class JobListResponse(BaseModel):
    """One batch of jobs and the token that continues it."""

    model_config = ConfigDict(from_attributes=True)

    items: list[JobSummary]
    next_cursor: str | None = Field(
        default=None,
        description="Pass back as `cursor` for the next batch. Null when the listing ends.",
    )


class SourceAttribution(BaseModel):
    """Where a job was found, as shown to a reader.

    Narrower than `ProvenanceRead`, which carries the provider's own record
    identifier, our source identifier, and when ingestion last saw the posting.
    A reader needs the board's name and the original posting; none of the rest
    is theirs to know, so this shape has nowhere to put it.
    """

    model_config = ConfigDict(from_attributes=True)

    key: str
    display_name: str
    url: HttpUrl

    @classmethod
    def of(cls, provenance: Any) -> "SourceAttribution":
        return cls(
            key=provenance.source.key,
            display_name=provenance.source.display_name,
            url=HttpUrl(provenance.source_url),
        )


class JobDetail(BaseModel):
    """One job, as served to a reader who opened it.

    Carries no ingestion timestamps and no path to a raw payload. A job may
    appear on several boards, so attribution is a list rather than one source.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company: CompanyRead
    title: str
    description: str
    location: str | None
    workplace_type: WorkplaceType
    employment_type: EmploymentType
    application_url: HttpUrl
    published_at: datetime | None
    expires_at: datetime | None
    status: JobStatus
    sources: list[SourceAttribution]

    @classmethod
    def of(cls, job: Any) -> "JobDetail":
        return cls(
            id=job.id,
            company=CompanyRead.model_validate(job.company),
            title=job.title,
            description=job.description,
            location=job.location,
            workplace_type=job.workplace_type,
            employment_type=job.employment_type,
            application_url=HttpUrl(job.application_url),
            published_at=job.published_at,
            expires_at=job.expires_at,
            status=job.status,
            sources=[SourceAttribution.of(record) for record in job.provenance_records],
        )

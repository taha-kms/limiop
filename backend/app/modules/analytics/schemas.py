"""What the job-market aggregates look like on the wire."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.analytics.queries import TrendBucket
from app.modules.jobs.domain import WorkplaceType

DEFAULT_GROUP_LIMIT = 20
MAXIMUM_GROUP_LIMIT = 100


class AnalyticsQuery(BaseModel):
    """The window and narrowing every aggregate accepts.

    Unknown parameters are refused rather than ignored, exactly as on the
    listing: a misspelled filter that is silently dropped returns the whole
    market and looks like a filter that matched everything.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    since: datetime | None = None
    until: datetime | None = None
    source_key: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=255)
    limit: int = Field(default=DEFAULT_GROUP_LIMIT, ge=1, le=MAXIMUM_GROUP_LIMIT)

    @model_validator(mode="after")
    def check_window(self) -> "AnalyticsQuery":
        """A window that ends before it starts is a mistake, not an empty result.

        Returning nothing would be a defensible answer and a useless one: the
        caller would read it as a market with no postings in it.
        """
        if self.since is not None and self.until is not None and self.until <= self.since:
            raise ValueError("until must be after since")
        return self


class TrendQuery(AnalyticsQuery):
    """A trend also chooses how finely to cut the window."""

    bucket: TrendBucket = TrendBucket.WEEK


class SkillDemand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    concept_id: UUID
    preferred_label: str
    jobs: int


class LocationCount(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    location: str
    jobs: int


class WorkplaceCount(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workplace_type: WorkplaceType
    jobs: int


class TrendPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bucket_start: datetime
    jobs: int


class SkillDemandResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    skills: tuple[SkillDemand, ...]


class LocationDistributionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    locations: tuple[LocationCount, ...]
    workplace_types: tuple[WorkplaceCount, ...]


class PostingTrendResponse(BaseModel):
    """A trend and the bucket it was cut with.

    Echoed rather than assumed by the reader: a series of counts means nothing
    without knowing whether a point is a day or a month.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    bucket: TrendBucket
    points: tuple[TrendPoint, ...]

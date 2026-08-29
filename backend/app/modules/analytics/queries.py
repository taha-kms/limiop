"""Job-market aggregates, computed from the canonical catalog.

Everything here counts `jobs` rows. That matters more than it looks: a job is
already the deduplicated entity, so a posting two sources describe is one row
with two provenance rows behind it. Counting postings-as-seen would inflate
every figure by however many boards happened to carry the same opening.

Only active jobs are counted. An expired posting is evidence about the past and
these questions are about the market now, so the status clause is not a filter a
caller can turn off — the same rule the public listing already applies.

Times are UTC throughout. `published_at` is stored with a timezone and bucketed
after conversion, so a bucket boundary means the same thing wherever the reader
is.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from platform_db.models import Job, JobProvenance, JobSource, SkillConcept
from platform_db.models.job_skills import JobSkill
from sqlalchemy import Select, func, select

from app.modules.jobs.domain import JobStatus, WorkplaceType

# What a location says when the source did not say one. Kept visible rather
# than dropped: how much of the market declines to state a place is itself an
# answer, and a silently smaller denominator makes every other row wrong.
UNKNOWN_LOCATION = "Unknown"


class TrendBucket(StrEnum):
    """How finely a trend is cut. PostgreSQL truncates to the same names."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"


@dataclass(frozen=True, slots=True)
class AnalyticsFilters:
    """The window and the narrowing every aggregate shares.

    Both bounds are optional and both are half-open where given: `since` is
    inclusive and `until` exclusive, so adjacent windows tile without counting a
    posting twice at the seam.
    """

    since: datetime | None = None
    until: datetime | None = None
    source_key: str | None = None
    location: str | None = None


def active_jobs() -> Select[tuple[Job]]:
    return select(Job).where(Job.status == JobStatus.ACTIVE)


def narrowed(statement: Select[tuple[Job]], filters: AnalyticsFilters) -> Select[tuple[Job]]:
    """Apply the shared window and filters to a statement over jobs."""
    if filters.since is not None:
        statement = statement.where(Job.published_at >= filters.since)
    if filters.until is not None:
        statement = statement.where(Job.published_at < filters.until)
    if filters.location is not None:
        statement = statement.where(Job.location == filters.location)
    if filters.source_key is not None:
        statement = statement.where(
            Job.id.in_(
                select(JobProvenance.job_id)
                .join(JobSource, JobSource.id == JobProvenance.source_id)
                .where(JobSource.key == filters.source_key)
            )
        )
    return statement


def _base(filters: AnalyticsFilters) -> Select[tuple[UUID]]:
    return narrowed(active_jobs(), filters).with_only_columns(Job.id)


def skill_demand(filters: AnalyticsFilters, limit: int) -> Select[tuple[UUID, str, int]]:
    """How many active jobs ask for each canonical skill, most first.

    Ties break on the label so two runs over unchanged data agree, which a
    chart with a cut-off needs in order to be reproducible.
    """
    jobs = _base(filters).subquery()
    return (
        select(
            SkillConcept.id,
            SkillConcept.preferred_label,
            func.count(JobSkill.job_id).label("jobs"),
        )
        .join(JobSkill, JobSkill.concept_id == SkillConcept.id)
        .join(jobs, jobs.c.id == JobSkill.job_id)
        .group_by(SkillConcept.id, SkillConcept.preferred_label)
        .order_by(func.count(JobSkill.job_id).desc(), SkillConcept.preferred_label)
        .limit(limit)
    )


def location_distribution(filters: AnalyticsFilters, limit: int) -> Select[tuple[str, int]]:
    """How many active jobs each stated location carries.

    Locations are grouped exactly as stored. Normalizing them here would invent
    a taxonomy this repository has not decided — `Berlin` and `Berlin, Germany`
    are two rows, and that is a visible fact about the sources rather than a
    hidden one.
    """
    location = func.coalesce(func.nullif(func.btrim(Job.location), ""), UNKNOWN_LOCATION)
    return (
        narrowed(active_jobs(), filters)
        .with_only_columns(location.label("location"), func.count(Job.id).label("jobs"))
        .group_by(location)
        .order_by(func.count(Job.id).desc(), location)
        .limit(limit)
    )


def workplace_distribution(filters: AnalyticsFilters) -> Select[tuple[WorkplaceType, int]]:
    """How the active market splits across remote, hybrid, onsite, and unstated.

    `unspecified` is a row rather than an omission. Most postings state nothing,
    and hiding that would make the remote share look like a share of the market
    when it is a share of the postings that said.
    """
    return (
        narrowed(active_jobs(), filters)
        .with_only_columns(Job.workplace_type, func.count(Job.id).label("jobs"))
        .group_by(Job.workplace_type)
        .order_by(func.count(Job.id).desc(), Job.workplace_type)
    )


def posting_trend(filters: AnalyticsFilters, bucket: TrendBucket) -> Select[tuple[datetime, int]]:
    """How many jobs were published per bucket, oldest first.

    Undated postings are excluded rather than bucketed somewhere: a job with no
    publication date belongs in no period, and putting it in one would be an
    invention the chart could not distinguish from a real observation.
    """
    # Three-argument date_trunc: the zone is named rather than inherited from
    # the server, and the result stays timezone-aware so a bucket boundary is
    # served as an instant rather than as a naive local-looking timestamp.
    truncated = func.date_trunc(bucket.value, Job.published_at, "UTC")
    return (
        narrowed(active_jobs(), filters)
        .where(Job.published_at.is_not(None))
        .with_only_columns(truncated.label("bucket"), func.count(Job.id).label("jobs"))
        .group_by(truncated)
        .order_by(truncated)
    )

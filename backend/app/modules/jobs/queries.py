"""Read-side queries for the job catalog.

One boundary between stored jobs and anything that serves them. Route handlers
call `list_jobs` and never build a statement, so filtering and paging rules stay
in one place and are testable without HTTP.

The catalog is public and continuously ingested. Both facts shape the paging:
readers are anonymous, so nothing here is scoped to a viewer, and rows arrive
between requests, so paging is keyset rather than offset. An offset window
shifts under a reader when a job is inserted above it, which shows the same job
twice partway down an infinite scroll.
"""

import base64
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, literal, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, selectinload

from app.modules.jobs.domain import EmploymentType, JobStatus, WorkplaceType
from app.modules.jobs.models import Job

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# A cursor names a position in one ordering. Bump this when the ordering
# changes, so cursors issued under the old one are refused rather than
# resolved against a sequence they no longer describe.
CURSOR_VERSION = "1"
CURSOR_SEPARATOR = "|"
CURSOR_FIELDS = 3


class InvalidCursorError(ValueError):
    """A cursor could not be read as a position in the catalog."""


@dataclass(frozen=True, slots=True)
class JobFilters:
    """Every filter the listing supports, all optional and freely combined.

    The two vocabulary filters take sets because a reader narrowing to remote
    work usually means remote or hybrid, not remote alone. An empty set means
    the filter is not applied, which keeps "no choice made" and "every choice
    made" from needing different call sites.
    """

    company_id: UUID | None = None
    location: str | None = None
    workplace_types: frozenset[WorkplaceType] = field(default_factory=frozenset)
    employment_types: frozenset[EmploymentType] = field(default_factory=frozenset)
    title_query: str | None = None


@dataclass(frozen=True, slots=True)
class JobCursor:
    """A reader's position, expressed as the sort key of the last row seen."""

    published_at: datetime | None
    job_id: UUID


@dataclass(frozen=True, slots=True)
class JobPage:
    """One batch, plus how to ask for the next one."""

    jobs: tuple[Job, ...]
    next_cursor: str | None

    @property
    def has_more(self) -> bool:
        return self.next_cursor is not None


def encode_cursor(cursor: JobCursor) -> str:
    """Render a position as the opaque token a client sends back.

    Base64 rather than readable text, and unsigned. The catalog is public, so a
    forged cursor reveals nothing a reader could not reach by scrolling, which
    makes a signature protect nothing worth protecting. Encoding still matters:
    a readable cursor becomes an API by accident, clients start building their
    own, and the sort order can never change again.

    The version prefix is the escape hatch for that. A cursor describes a
    position in one specific ordering, so changing the ordering bumps the
    version and old cursors are refused instead of quietly paging wrong.
    """
    published = cursor.published_at.isoformat() if cursor.published_at is not None else ""
    payload = CURSOR_SEPARATOR.join((CURSOR_VERSION, published, str(cursor.job_id)))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(token: str) -> JobCursor:
    """Read a client-supplied token back into a position.

    Everything unreadable raises. Falling back to the top of the catalog would
    turn a corrupt token into a scroll that silently jumps to the newest job,
    which a reader experiences as the page losing their place rather than as an
    error, and which nothing downstream could detect.
    """
    padded = token + "=" * (-len(token) % 4)
    try:
        payload = base64.b64decode(padded, altchars=b"-_", validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as error:
        raise InvalidCursorError("cursor is not a readable token") from error

    fields = payload.split(CURSOR_SEPARATOR)
    if len(fields) != CURSOR_FIELDS:
        raise InvalidCursorError("cursor does not describe a position")

    version, published, job_id = fields
    if version != CURSOR_VERSION:
        raise InvalidCursorError("cursor was issued under a different ordering")

    try:
        parsed = datetime.fromisoformat(published) if published else None
        identifier = UUID(job_id)
    except ValueError as error:
        raise InvalidCursorError("cursor does not describe a position") from error

    if parsed is not None and parsed.utcoffset() is None:
        raise InvalidCursorError("cursor timestamp carries no time zone")

    return JobCursor(published_at=parsed, job_id=identifier)


ORDER_BY = (Job.published_at.desc().nullslast(), Job.id.desc())


def contains(
    column: InstrumentedAttribute[str] | InstrumentedAttribute[str | None],
    value: str,
) -> ColumnElement[bool]:
    """Case-insensitive substring match over caller-supplied text.

    The wildcards are escaped before the pattern is built. Without that, a
    reader searching for `C_` or `100%` would be handing the database a pattern
    instead of a term, and would silently get matches they never asked for.
    """
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


def apply_filters(statement: Select[tuple[Job]], filters: JobFilters) -> Select[tuple[Job]]:
    """Narrow a statement to the listable jobs a reader asked for.

    The status clause is not a filter the caller can turn off. Only active jobs
    are listable, and nothing assigns any other status yet, so this has to be
    right before it starts mattering rather than after.
    """
    statement = statement.where(Job.status == JobStatus.ACTIVE)
    if filters.company_id is not None:
        statement = statement.where(Job.company_id == filters.company_id)
    if filters.location is not None:
        statement = statement.where(contains(Job.location, filters.location))
    if filters.workplace_types:
        statement = statement.where(Job.workplace_type.in_(filters.workplace_types))
    if filters.employment_types:
        statement = statement.where(Job.employment_type.in_(filters.employment_types))
    if filters.title_query is not None:
        statement = statement.where(contains(Job.title, filters.title_query))
    return statement


def after(cursor: JobCursor) -> ColumnElement[bool]:
    """Rows strictly after a position in `published_at DESC NULLS LAST, id DESC`.

    Undated jobs occupy the tail, so they follow every dated job whatever the
    cursor holds, and order among themselves by id alone. Reaching the tail is
    therefore one-way: once the cursor carries no date, no dated job can appear
    again.
    """
    if cursor.published_at is None:
        return and_(Job.published_at.is_(None), Job.id < cursor.job_id)
    return or_(
        Job.published_at.is_(None),
        tuple_(Job.published_at, Job.id)
        < tuple_(literal(cursor.published_at), literal(cursor.job_id)),
    )


async def list_jobs(
    session: AsyncSession,
    *,
    filters: JobFilters | None = None,
    cursor: str | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> JobPage:
    """Read one batch of listable jobs, newest first.

    One row beyond the batch is fetched to learn whether another batch exists,
    which avoids a second count query that would be wrong by the time it
    returned anyway.
    """
    if page_size < 1:
        raise ValueError("page_size must be at least 1")

    size = min(page_size, MAX_PAGE_SIZE)
    statement = apply_filters(
        select(Job).options(selectinload(Job.company)),
        filters if filters is not None else JobFilters(),
    )
    if cursor is not None:
        statement = statement.where(after(decode_cursor(cursor)))

    rows = tuple((await session.scalars(statement.order_by(*ORDER_BY).limit(size + 1))).all())
    if len(rows) <= size:
        return JobPage(jobs=rows, next_cursor=None)

    batch = rows[:size]
    last = batch[-1]
    return JobPage(
        jobs=batch,
        next_cursor=encode_cursor(JobCursor(published_at=last.published_at, job_id=last.id)),
    )

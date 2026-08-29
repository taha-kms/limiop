"""HTTP surface for the public job catalog.

The catalog is readable without an account, so nothing here is scoped to a
viewer. Handlers stay thin: they parse, delegate to the query service, and
translate its failures into status codes. No statement is built here.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_database_session
from app.modules.jobs.queries import (
    InvalidCursorError,
    UnknownSourceError,
    get_job,
    list_jobs,
    list_sources,
)
from app.modules.jobs.schemas import (
    JobDetail,
    JobListQuery,
    JobListResponse,
    JobSummary,
    SourceListResponse,
    SourceRead,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get(
    "",
    response_model=JobListResponse,
    status_code=status.HTTP_200_OK,
    summary="Browse the job catalog",
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "The cursor could not be read"},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "A filter names nothing"},
    },
)
async def list_job_postings(
    query: Annotated[JobListQuery, Query()],
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> JobListResponse:
    """Return one batch of listable jobs, newest first.

    A cursor is only meaningful inside the filter set that produced it, so a
    caller changing a filter starts over without one. A cursor that cannot be
    read is a client error rather than a silent restart at the newest job, which
    a reader would experience as the page losing their place.
    """
    try:
        page = await list_jobs(
            session,
            filters=query.to_filters(),
            cursor=query.cursor,
            page_size=query.limit,
        )
    except InvalidCursorError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The cursor is not a position in this listing. Start without one.",
        ) from error
    except UnknownSourceError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"No source is called {error.key!r}. Ask /jobs/sources which there are.",
        ) from error

    items = [JobSummary.of(job) for job in page.jobs]
    return JobListResponse(items=items, next_cursor=page.next_cursor)


@router.get(
    "/sources",
    response_model=SourceListResponse,
    status_code=status.HTTP_200_OK,
    summary="List the boards the catalog ingests",
)
async def list_job_sources(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> SourceListResponse:
    """Return every registered source, so a client can offer the source filter.

    Declared before the detail route because FastAPI matches in declaration
    order, and `/jobs/{job_id}` would otherwise read `sources` as an identifier.
    """
    sources = await list_sources(session)
    return SourceListResponse(sources=[SourceRead.model_validate(source) for source in sources])


@router.get(
    "/{job_id}",
    response_model=JobDetail,
    status_code=status.HTTP_200_OK,
    summary="Read one job",
    responses={status.HTTP_404_NOT_FOUND: {"description": "No such job"}},
)
async def read_job_posting(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> JobDetail:
    """Return one job, whatever its status.

    A job that lapsed is still served, because the only way to reach one is a
    link saved before it did, and telling a reader the posting closed is more
    use than telling them it never existed. Its status says which.
    """
    job = await get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such job.")
    return JobDetail.of(job)

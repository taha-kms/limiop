"""HTTP surface for the public job catalog.

The catalog is readable without an account, so nothing here is scoped to a
viewer. Handlers stay thin: they parse, delegate to the query service, and
translate its failures into status codes. No statement is built here.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_database_session
from app.modules.jobs.queries import InvalidCursorError, list_jobs
from app.modules.jobs.schemas import JobListQuery, JobListResponse, JobSummary

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get(
    "",
    response_model=JobListResponse,
    status_code=status.HTTP_200_OK,
    summary="Browse the job catalog",
    responses={status.HTTP_400_BAD_REQUEST: {"description": "The cursor could not be read"}},
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

    items = [JobSummary.model_validate(job) for job in page.jobs]
    return JobListResponse(items=items, next_cursor=page.next_cursor)

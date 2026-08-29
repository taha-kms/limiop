"""Liveness, readiness, and whether the catalogue is still being fed.

Three endpoints because they answer three questions. Liveness decides whether to
restart this process and touches nothing external — a probe that talks to the
database turns one outage into a restart loop. Readiness decides whether to
send traffic here, so it checks what a request actually needs.

The third is neither. Ingestion runs elsewhere, on a schedule, unattended, and
a stalled pipeline serves a catalogue that is merely getting staler — which is
worth seeing and is not a reason to take this process out of rotation. So it
reports and never fails.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_database_session
from app.core.config import Settings
from app.modules.ingestion.queries import read_latest_runs
from app.modules.ingestion.schemas import IngestionRunReport, IngestionStatusResponse
from app.observability.readiness import DependencyState, check_database, check_storage
from app.schemas.health import DependencyStatus, HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Whether this process is alive",
)
def health_check() -> HealthResponse:
    """Deliberately does no work. A dependency being down is not a reason to
    restart a healthy process."""
    return HealthResponse(status="ok")


@router.get(
    "/health/ready",
    summary="Whether this process can serve",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "A dependency is unusable"}},
)
async def readiness_check(request: Request, response: Response) -> ReadinessResponse:
    """Check every dependency a request needs, each with its own timeout.

    Reports 503 when any is unusable, because a load balancer reads the status
    code and a body saying `degraded` under a 200 is a body nobody reads.
    """
    settings: Settings = request.app.state.settings
    reports = [
        await check_database(request.app.state.database.engine),
        await check_storage(settings.cv_storage_root),
    ]
    degraded = any(report.state is DependencyState.DOWN for report in reports)
    if degraded:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="degraded" if degraded else "ready",
        dependencies=tuple(
            DependencyStatus(name=report.name, state=report.state, reason=report.reason)
            for report in reports
        ),
    )


@router.get(
    "/health/ingestion",
    summary="What each source's most recent run did",
)
async def ingestion_status(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> IngestionStatusResponse:
    """Report the most recent run of every source that has ever run.

    Always 200, including when the last run failed. A failed ingestion is not a
    reason to stop sending traffic here, and a status code that says otherwise
    would eventually be wired into something that acts on it.
    """
    runs = await read_latest_runs(session)
    return IngestionStatusResponse(runs=[IngestionRunReport.of(run) for run in runs])

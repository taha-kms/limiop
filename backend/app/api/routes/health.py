"""Liveness and readiness.

Two endpoints because they answer two questions. Liveness decides whether to
restart this process and touches nothing external — a probe that talks to the
database turns one outage into a restart loop. Readiness decides whether to
send traffic here, so it checks what a request actually needs.
"""

from fastapi import APIRouter, Request, Response, status

from app.core.config import Settings
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

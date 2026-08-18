from fastapi import APIRouter, status

from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Check API health",
)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")

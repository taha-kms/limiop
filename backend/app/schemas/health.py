from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.observability.readiness import DependencyState


class HealthResponse(BaseModel):
    """Liveness. Says only that this process is running and answering."""

    status: Literal["ok"]


class DependencyStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    state: DependencyState
    reason: str | None = None


class ReadinessResponse(BaseModel):
    """Readiness, and which dependency is why when it is not ready."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ready", "degraded"]
    dependencies: tuple[DependencyStatus, ...]

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.modules.cvs.models import CVProcessingState


class CVRead(BaseModel):
    id: UUID
    media_type: str
    size_bytes: int
    processing_state: CVProcessingState
    created_at: AwareDatetime

    model_config = ConfigDict(from_attributes=True)

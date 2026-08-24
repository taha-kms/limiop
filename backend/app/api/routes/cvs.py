from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    CurrentUser,
    get_application_settings,
    get_cv_storage,
    get_database_session,
)
from app.core.config import Settings
from app.modules.cvs.policy import CVUploadPolicy, CVUploadRejected, UploadRejectionReason
from app.modules.cvs.schemas import CVRead
from app.modules.cvs.service import CVMetadataPersistenceError, intake_cv
from app.modules.cvs.storage import CVObjectTooLarge, CVStorage, CVStorageError

router = APIRouter(prefix="/api/v1/cvs", tags=["cvs"])


@router.post(
    "",
    response_model=CVRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a CV",
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "The file or filename is invalid"},
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication is required"},
        status.HTTP_413_CONTENT_TOO_LARGE: {"description": "The file exceeds the limit"},
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {"description": "The file is not a PDF"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "The upload could not be stored"},
    },
)
async def upload_cv(
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_application_settings)],
    storage: Annotated[CVStorage, Depends(get_cv_storage)],
    file: Annotated[UploadFile, File(description="PDF CV")],
) -> CVRead:
    policy = CVUploadPolicy(
        max_bytes=settings.cv_max_upload_bytes,
        allowed_formats=frozenset(settings.cv_allowed_formats),
    )
    try:
        cv = await intake_cv(
            session,
            storage,
            owner_id=user.id,
            upload=file,
            policy=policy,
        )
    except CVUploadRejected as error:
        raise HTTPException(
            status_code=_policy_status(error.reason),
            detail={"code": error.reason.value, "message": str(error)},
        ) from None
    except CVObjectTooLarge:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={
                "code": UploadRejectionReason.FILE_TOO_LARGE.value,
                "message": "the upload exceeds the configured size limit",
            },
        ) from None
    except (CVStorageError, CVMetadataPersistenceError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="the CV could not be stored",
        ) from None
    return CVRead.model_validate(cv)


def _policy_status(reason: UploadRejectionReason) -> int:
    if reason is UploadRejectionReason.FILE_TOO_LARGE:
        return status.HTTP_413_CONTENT_TOO_LARGE
    if reason in (
        UploadRejectionReason.UNSUPPORTED_MEDIA_TYPE,
        UploadRejectionReason.UNSUPPORTED_CONTENT,
    ):
        return status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    return status.HTTP_400_BAD_REQUEST

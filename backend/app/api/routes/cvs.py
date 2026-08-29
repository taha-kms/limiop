from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    CurrentUser,
    get_application_settings,
    get_cv_storage,
    get_database,
    get_database_session,
)
from app.core.config import Settings
from app.db.session import Database
from app.modules.cvs.models import CV
from app.modules.cvs.parsing import PDFParserLimits
from app.modules.cvs.policy import CVUploadPolicy, CVUploadRejected, UploadRejectionReason
from app.modules.cvs.processing import process_cv
from app.modules.cvs.schemas import CVRead
from app.modules.cvs.service import (
    CVMetadataPersistenceError,
    CVNotFound,
    delete_cv,
    intake_cv,
)
from app.modules.cvs.storage import CVObjectTooLarge, CVStorage, CVStorageError

router = APIRouter(prefix="/api/v1/cvs", tags=["cvs"])


@router.post(
    "",
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
    background: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_database_session)],
    database: Annotated[Database, Depends(get_database)],
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
    # Queued rather than awaited. Parsing spawns a process with a timeout, and
    # holding the upload open for it makes its latency a function of whatever
    # PDF somebody chose. The row records `pending` until it runs, so a CV
    # whose processing was lost is visibly unprocessed rather than silently
    # missing its skills.
    background.add_task(
        process_cv,
        database,
        storage,
        cv_id=cv.id,
        limits=PDFParserLimits(
            max_file_bytes=settings.cv_max_upload_bytes,
            max_pages=settings.cv_pdf_max_pages,
            max_text_characters=settings.cv_pdf_max_text_characters,
            timeout_seconds=settings.cv_pdf_timeout_seconds,
        ),
    )
    return CVRead.model_validate(cv)


@router.get("", summary="The CV you last uploaded")
async def read_cv(
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> CVRead | None:
    """The owner's most recent CV, or null when there is none.

    Scoped by the session. There is no identifier a caller could supply to read
    somebody else's, and the body carries metadata rather than any of the
    document's contents.
    """
    latest = (
        (
            await session.execute(
                select(CV).where(CV.owner_id == user.id).order_by(CV.created_at.desc()).limit(1)
            )
        )
        .scalars()
        .first()
    )
    return CVRead.model_validate(latest) if latest is not None else None


@router.delete(
    "/{cv_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a CV",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication is required"},
        status.HTTP_404_NOT_FOUND: {"description": "No such CV"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "The CV could not be deleted"},
    },
)
async def remove_cv(
    cv_id: UUID,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_database_session)],
    storage: Annotated[CVStorage, Depends(get_cv_storage)],
) -> None:
    """Delete the caller's CV, the stored file, and the skills it inferred.

    A CV that is not the caller's answers exactly as one that never existed, so
    the endpoint cannot be used to find out which identifiers are real. Deleting
    the same CV twice therefore says "no such CV" the second time.
    """
    try:
        await delete_cv(session, storage, cv_id=cv_id, owner_id=user.id)
    except CVNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such CV") from None
    except CVStorageError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="the CV could not be deleted",
        ) from None


def _policy_status(reason: UploadRejectionReason) -> int:
    if reason is UploadRejectionReason.FILE_TOO_LARGE:
        return status.HTTP_413_CONTENT_TOO_LARGE
    if reason in (
        UploadRejectionReason.UNSUPPORTED_MEDIA_TYPE,
        UploadRejectionReason.UNSUPPORTED_CONTENT,
    ):
        return status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    return status.HTTP_400_BAD_REQUEST

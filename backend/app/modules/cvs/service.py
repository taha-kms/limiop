"""Coordinate a bounded upload across policy, object storage, and metadata."""

from contextlib import suppress
from functools import partial
from tempfile import SpooledTemporaryFile
from typing import IO, Protocol
from uuid import UUID

from anyio import to_thread
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cvs.models import CV
from app.modules.cvs.policy import PDF_MAGIC, AcceptedCVUpload, CVUploadPolicy
from app.modules.cvs.storage import CVStorage, CVStorageError
from app.modules.profiles.models import CandidateProfile, CandidateProfileSkill, SkillSource

UPLOAD_CHUNK_BYTES = 64 * 1024
UPLOAD_MEMORY_SPOOL_BYTES = 1024 * 1024


class UploadStream(Protocol):
    filename: str | None
    content_type: str | None

    async def read(self, size: int = -1) -> bytes: ...

    async def close(self) -> None: ...


class CVMetadataPersistenceError(Exception):
    """The object was stored but its database record could not be committed."""


class CVNotFound(LookupError):
    """No CV with that identifier belongs to this owner."""


async def copy_upload_bounded(
    upload: UploadStream,
    target: IO[bytes],
    *,
    max_bytes: int,
) -> tuple[int, bytes]:
    """Copy no more than the limit plus one byte, enough to prove overflow."""
    size_bytes = 0
    initial_bytes = b""
    while size_bytes <= max_bytes:
        read_size = min(UPLOAD_CHUNK_BYTES, max_bytes - size_bytes + 1)
        chunk = await upload.read(read_size)
        if not chunk:
            break
        size_bytes += len(chunk)
        if len(initial_bytes) < len(PDF_MAGIC):
            initial_bytes = (initial_bytes + chunk)[: len(PDF_MAGIC)]
        await to_thread.run_sync(target.write, chunk)
        if size_bytes > max_bytes:
            break
    return size_bytes, initial_bytes


async def intake_cv(
    session: AsyncSession,
    storage: CVStorage,
    *,
    owner_id: UUID,
    upload: UploadStream,
    policy: CVUploadPolicy,
) -> CV:
    try:
        spool = await to_thread.run_sync(
            partial(
                SpooledTemporaryFile,
                max_size=min(UPLOAD_MEMORY_SPOOL_BYTES, policy.max_bytes),
                mode="w+b",
            )
        )
        try:
            size_bytes, initial_bytes = await copy_upload_bounded(
                upload,
                spool,
                max_bytes=policy.max_bytes,
            )
            accepted = policy.validate(
                client_filename=upload.filename,
                declared_media_type=upload.content_type,
                size_bytes=size_bytes,
                initial_bytes=initial_bytes,
            )
            await to_thread.run_sync(spool.seek, 0)
            stored = await storage.write(owner_id, spool, max_bytes=policy.max_bytes)
            cv = _metadata(owner_id, accepted, stored.key, stored.checksum_sha256)
            try:
                session.add(cv)
                await session.flush()
                await session.refresh(cv)
                await session.commit()
            except SQLAlchemyError:
                await session.rollback()
                with suppress(CVStorageError):
                    await storage.delete(stored.key)
                raise CVMetadataPersistenceError("the CV metadata could not be stored") from None
            return cv
        finally:
            # An upload past the spool threshold has rolled over to a real
            # file, so closing it flushes and unlinks on disk. That is the one
            # blocking call the surrounding offloading missed.
            await to_thread.run_sync(spool.close)
    finally:
        with suppress(OSError):
            await upload.close()


def _metadata(
    owner_id: UUID,
    accepted: AcceptedCVUpload,
    storage_key: str,
    checksum_sha256: str,
) -> CV:
    return CV(
        owner_id=owner_id,
        storage_key=storage_key,
        checksum_sha256=checksum_sha256,
        media_type=accepted.media_type,
        size_bytes=accepted.size_bytes,
    )


async def delete_cv(
    session: AsyncSession,
    storage: CVStorage,
    *,
    cv_id: UUID,
    owner_id: UUID,
) -> None:
    """Remove a CV: its stored bytes, its metadata, and the skills it inferred.

    Scoped to the owner. A CV that belongs to somebody else is not found rather
    than refused, so the endpoint cannot be used to learn that an identifier
    names a real document.

    The object goes before the row, because the row is what makes a retry
    possible. A failed object delete leaves both and the caller can ask again;
    the other order would leave bytes nothing points at, which is exactly what
    the upload policy promises not to keep.

    The row is taken with `FOR UPDATE` first, before anything is removed. A CV
    can be read in the background while this runs, and that read takes the same
    row: without the lock here, this could delete the skills that existed before
    the read and then wait while the read wrote new ones, leaving a profile
    holding skills from a CV that no longer exists.

    The skills the CV wrote go with it, but only when this is the CV that wrote
    them. `store_cv_skills` replaces every CV-sourced row on each read, so they
    belong to the owner's most recent CV; deleting an older one must leave them
    alone. A concept the candidate picked by hand is `manual` and survives
    either way, because deleting a document is not withdrawing a choice.
    """
    cv = await session.scalar(
        select(CV).where(CV.id == cv_id, CV.owner_id == owner_id).with_for_update()
    )
    if cv is None:
        raise CVNotFound

    await storage.delete(cv.storage_key)
    if await _is_most_recent(session, cv):
        await session.execute(
            delete(CandidateProfileSkill).where(
                CandidateProfileSkill.source == SkillSource.CV,
                CandidateProfileSkill.profile_id.in_(
                    select(CandidateProfile.id).where(CandidateProfile.user_id == owner_id)
                ),
            )
        )
    await session.delete(cv)
    await session.commit()


async def _is_most_recent(session: AsyncSession, cv: CV) -> bool:
    """Whether this is the owner's newest CV, and so the one that wrote the skills."""
    newest = await session.scalar(
        select(CV.id).where(CV.owner_id == cv.owner_id).order_by(CV.created_at.desc()).limit(1)
    )
    return newest == cv.id

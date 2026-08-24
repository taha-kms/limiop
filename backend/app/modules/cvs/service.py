"""Coordinate a bounded upload across policy, object storage, and metadata."""

from contextlib import suppress
from tempfile import SpooledTemporaryFile
from typing import IO, Protocol
from uuid import UUID

from anyio import to_thread
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cvs.models import CV
from app.modules.cvs.policy import PDF_MAGIC, AcceptedCVUpload, CVUploadPolicy
from app.modules.cvs.storage import CVStorage, CVStorageError

UPLOAD_CHUNK_BYTES = 64 * 1024
UPLOAD_MEMORY_SPOOL_BYTES = 1024 * 1024


class UploadStream(Protocol):
    filename: str | None
    content_type: str | None

    async def read(self, size: int = -1) -> bytes: ...

    async def close(self) -> None: ...


class CVMetadataPersistenceError(Exception):
    """The object was stored but its database record could not be committed."""


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
        with SpooledTemporaryFile(
            max_size=min(UPLOAD_MEMORY_SPOOL_BYTES, policy.max_bytes),
            mode="w+b",
        ) as spool:
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

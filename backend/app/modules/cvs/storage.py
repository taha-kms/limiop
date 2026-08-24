"""A narrow CV object-storage seam and the local filesystem implementation."""

import hashlib
import os
import re
import tempfile
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID, uuid4

from anyio import to_thread

KEY_PART = re.compile(r"^[0-9a-f]{32}$")
OBJECT_NAME = re.compile(r"^[0-9a-f]{32}\.pdf$")


class CVStorageError(Exception):
    """Expected storage failure whose message contains no data or host path."""


class InvalidCVStorageKey(CVStorageError):
    pass


class CVStorageCollision(CVStorageError):
    pass


class CVObjectNotFound(CVStorageError):
    pass


class CVObjectTooLarge(CVStorageError):
    pass


@dataclass(frozen=True, slots=True)
class StoredCVObject:
    key: str
    checksum_sha256: str
    size_bytes: int


class CVStorage(Protocol):
    async def write(self, owner_id: UUID, content: bytes) -> StoredCVObject: ...

    async def read(self, key: str, *, max_bytes: int) -> bytes: ...

    async def delete(self, key: str) -> None: ...


class FilesystemCVStorage:
    """Store local-development CVs without exposing paths to callers."""

    def __init__(
        self,
        root: Path,
        *,
        object_id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._root = root
        self._object_id_factory = object_id_factory

    async def write(self, owner_id: UUID, content: bytes) -> StoredCVObject:
        return await to_thread.run_sync(self._write, owner_id, content)

    async def read(self, key: str, *, max_bytes: int) -> bytes:
        if max_bytes < 1:
            raise ValueError("CV read limit must be positive")
        return await to_thread.run_sync(self._read, key, max_bytes)

    async def delete(self, key: str) -> None:
        await to_thread.run_sync(self._delete, key)

    def _write(self, owner_id: UUID, content: bytes) -> StoredCVObject:
        key = f"{owner_id.hex}/{self._object_id_factory().hex}.pdf"
        destination = self._path_for_key(key)
        temporary_path: Path | None = None
        try:
            try:
                self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
                self._root.chmod(0o700)
                destination.parent.mkdir(mode=0o700, exist_ok=True)
                destination.parent.chmod(0o700)
                descriptor, temporary_name = tempfile.mkstemp(
                    dir=destination.parent,
                    prefix=".upload-",
                )
                temporary_path = Path(temporary_name)
                with os.fdopen(descriptor, "wb") as temporary:
                    temporary.write(content)
                    temporary.flush()
                    os.fsync(temporary.fileno())
            except OSError:
                raise CVStorageError("the CV object could not be stored") from None

            try:
                # A hard link publishes the complete temporary file atomically and
                # refuses an existing destination instead of overwriting it.
                os.link(temporary_path, destination)
            except FileExistsError:
                raise CVStorageCollision("the generated CV object key already exists") from None
            except OSError:
                raise CVStorageError("the CV object could not be stored") from None
        finally:
            if temporary_path is not None:
                with suppress(OSError):
                    temporary_path.unlink(missing_ok=True)

        return StoredCVObject(
            key=key,
            checksum_sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
        )

    def _read(self, key: str, max_bytes: int) -> bytes:
        path = self._path_for_key(key)
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as stored:
                content = stored.read(max_bytes + 1)
        except FileNotFoundError:
            raise CVObjectNotFound("the CV object does not exist") from None
        except OSError:
            raise CVStorageError("the CV object could not be read") from None
        if len(content) > max_bytes:
            raise CVObjectTooLarge("the CV object exceeds the read limit")
        return content

    def _delete(self, key: str) -> None:
        path = self._path_for_key(key)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            raise CVStorageError("the CV object could not be deleted") from None

    def _path_for_key(self, key: str) -> Path:
        pure_key = PurePosixPath(key)
        parts = pure_key.parts
        if (
            pure_key.is_absolute()
            or len(parts) != 2
            or KEY_PART.fullmatch(parts[0]) is None
            or OBJECT_NAME.fullmatch(parts[1]) is None
        ):
            raise InvalidCVStorageKey("the CV storage key is invalid")
        return self._root.joinpath(*parts)

import asyncio
import os
from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.modules.cvs.storage import (
    CVObjectNotFound,
    CVObjectTooLarge,
    CVStorageCollision,
    CVStorageError,
    FilesystemCVStorage,
    InvalidCVStorageKey,
)


def run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(awaitable)


def test_a_write_generates_an_opaque_key_and_integrity_metadata(tmp_path: Path) -> None:
    owner_id = uuid4()
    object_id = uuid4()
    storage = FilesystemCVStorage(tmp_path, object_id_factory=lambda: object_id)

    stored = run(storage.write(owner_id, b"%PDF-private"))

    assert stored.key == f"{owner_id.hex}/{object_id.hex}.pdf"
    assert stored.checksum_sha256 == (
        "9c747fd6ea592c2d09ae816761e81117b5fd7eff6a0eae7e30dde45bf9fb6fa9"
    )
    assert stored.size_bytes == 12
    assert run(storage.read(stored.key, max_bytes=12)) == b"%PDF-private"
    assert not list(tmp_path.rglob(".upload-*"))


def test_storage_directories_are_private_to_the_process_user(tmp_path: Path) -> None:
    owner_id = uuid4()
    storage = FilesystemCVStorage(tmp_path, object_id_factory=uuid4)
    stored = run(storage.write(owner_id, b"content"))

    assert tmp_path.stat().st_mode & 0o077 == 0
    assert (tmp_path / owner_id.hex).stat().st_mode & 0o077 == 0
    assert (tmp_path / stored.key).stat().st_mode & 0o077 == 0


@pytest.mark.parametrize(
    "key",
    [
        "",
        "../secret.pdf",
        "/etc/passwd",
        "owner/../../secret.pdf",
        "not-a-uuid/object.pdf",
        f"{uuid4().hex}/not-a-uuid.pdf",
        f"{uuid4().hex}/{uuid4().hex}.PDF",
        f"{uuid4().hex}\\{uuid4().hex}.pdf",
    ],
)
def test_reads_and_deletes_reject_keys_outside_the_generated_shape(
    tmp_path: Path, key: str
) -> None:
    storage = FilesystemCVStorage(tmp_path)

    with pytest.raises(InvalidCVStorageKey):
        run(storage.read(key, max_bytes=1024))
    with pytest.raises(InvalidCVStorageKey):
        run(storage.delete(key))


def test_a_key_collision_never_overwrites_the_first_object(tmp_path: Path) -> None:
    owner_id = uuid4()
    object_id = uuid4()
    storage = FilesystemCVStorage(tmp_path, object_id_factory=lambda: object_id)
    first = run(storage.write(owner_id, b"first"))

    with pytest.raises(CVStorageCollision):
        run(storage.write(owner_id, b"second-private-content"))

    assert run(storage.read(first.key, max_bytes=5)) == b"first"
    assert not list(tmp_path.rglob(".upload-*"))


def test_delete_is_explicit_and_idempotent(tmp_path: Path) -> None:
    storage = FilesystemCVStorage(tmp_path)
    stored = run(storage.write(uuid4(), b"content"))

    assert run(storage.delete(stored.key)) is None
    assert run(storage.delete(stored.key)) is None
    with pytest.raises(CVObjectNotFound):
        run(storage.read(stored.key, max_bytes=1024))


def test_reads_stop_at_the_caller_limit(tmp_path: Path) -> None:
    storage = FilesystemCVStorage(tmp_path)
    stored = run(storage.write(uuid4(), b"sensitive content"))

    with pytest.raises(CVObjectTooLarge) as raised:
        run(storage.read(stored.key, max_bytes=4))

    assert "sensitive content" not in str(raised.value)
    with pytest.raises(ValueError, match="positive"):
        run(storage.read(stored.key, max_bytes=0))


def test_a_failed_publish_cleans_up_and_hides_paths_and_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_root = tmp_path / "private-host-path"
    storage = FilesystemCVStorage(private_root)

    def refuse_link(_source: Path, _destination: Path) -> None:
        raise PermissionError("host path and private bytes")

    monkeypatch.setattr(os, "link", refuse_link)
    with pytest.raises(CVStorageError) as raised:
        run(storage.write(uuid4(), b"private bytes"))

    assert str(private_root) not in str(raised.value)
    assert "private bytes" not in str(raised.value)
    assert not [path for path in private_root.rglob("*") if path.is_file()]


def test_a_missing_object_error_does_not_expose_the_storage_root(tmp_path: Path) -> None:
    storage = FilesystemCVStorage(tmp_path / "private-host-path")
    key = f"{UUID(int=1).hex}/{UUID(int=2).hex}.pdf"

    with pytest.raises(CVObjectNotFound) as raised:
        run(storage.read(key, max_bytes=1024))

    assert str(tmp_path) not in str(raised.value)


def test_a_storage_setup_failure_is_generic(tmp_path: Path) -> None:
    root_that_is_a_file = tmp_path / "private-host-path"
    root_that_is_a_file.write_bytes(b"private bytes")
    storage = FilesystemCVStorage(root_that_is_a_file)

    with pytest.raises(CVStorageError) as raised:
        run(storage.write(uuid4(), b"sensitive content"))

    assert not isinstance(raised.value, CVStorageCollision)
    assert str(root_that_is_a_file) not in str(raised.value)
    assert "sensitive content" not in str(raised.value)


def test_a_read_failure_is_generic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = FilesystemCVStorage(tmp_path)
    key = f"{UUID(int=1).hex}/{UUID(int=2).hex}.pdf"

    def refuse_open(_path: Path, _flags: int) -> int:
        raise PermissionError("private host path")

    monkeypatch.setattr(os, "open", refuse_open)
    with pytest.raises(CVStorageError) as raised:
        run(storage.read(key, max_bytes=1024))

    assert not isinstance(raised.value, CVObjectNotFound)
    assert "private host path" not in str(raised.value)


def test_a_delete_failure_is_generic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = FilesystemCVStorage(tmp_path)
    key = f"{UUID(int=1).hex}/{UUID(int=2).hex}.pdf"

    def refuse_delete(_path: Path, *, missing_ok: bool = False) -> None:
        del missing_ok
        raise PermissionError("private host path")

    monkeypatch.setattr(Path, "unlink", refuse_delete)
    with pytest.raises(CVStorageError) as raised:
        run(storage.delete(key))

    assert "private host path" not in str(raised.value)

import asyncio
import hashlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from tempfile import SpooledTemporaryFile
from typing import IO, Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import PostgresDsn
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Environment, Settings
from app.main import create_app
from app.modules.cvs import service
from app.modules.cvs.storage import (
    CVObjectNotFound,
    CVObjectTooLarge,
    CVStorageError,
    StoredCVObject,
)

pytestmark = pytest.mark.integration

CREDENTIALS = {"email": "ada@example.com", "password": "correct horse battery staple"}
PDF = b"%PDF-1.7\nCV"


@dataclass
class FakeCVStorage:
    objects: dict[str, bytes] = field(default_factory=dict)
    writes: list[tuple[UUID, str]] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    fail_write: bool = False
    fail_delete: bool = False
    fail_too_large: bool = False

    async def write(self, owner_id: UUID, content: IO[bytes], *, max_bytes: int) -> StoredCVObject:
        if self.fail_write:
            raise CVStorageError("storage unavailable")
        if self.fail_too_large:
            raise CVObjectTooLarge("private storage detail")
        payload = content.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise CVObjectTooLarge("object too large")
        object_id = UUID(int=len(self.writes) + 1)
        key = f"{owner_id.hex}/{object_id.hex}.pdf"
        self.objects[key] = payload
        self.writes.append((owner_id, key))
        return StoredCVObject(
            key=key,
            checksum_sha256=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
        )

    async def read(self, key: str, *, max_bytes: int) -> bytes:
        try:
            payload = self.objects[key]
        except KeyError:
            raise CVObjectNotFound("object not found") from None
        if len(payload) > max_bytes:
            raise CVObjectTooLarge("object too large")
        return payload

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        if self.fail_delete:
            raise CVStorageError("delete unavailable")
        self.objects.pop(key, None)


@dataclass
class CVClient:
    client: TestClient
    storage: FakeCVStorage
    database_url: PostgresDsn


@pytest.fixture
def cv_client(database_url: PostgresDsn) -> Iterator[CVClient]:
    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))
    storage = FakeCVStorage()
    application = create_app(
        Settings(
            app_name="SkillSync Test API",
            environment=Environment.TEST,
            database_url=database_url,
            cv_max_upload_bytes=16,
        ),
        cv_storage=storage,
    )
    try:
        with TestClient(application) as client:
            yield CVClient(client, storage, database_url)
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM users"))
        engine.dispose()


def sign_in(context: CVClient) -> UUID:
    registered = context.client.post("/api/v1/accounts", json=CREDENTIALS)
    assert registered.status_code == 201
    logged_in = context.client.post("/api/v1/sessions", json=CREDENTIALS)
    assert logged_in.status_code == 204
    return UUID(registered.json()["id"])


def upload(
    context: CVClient,
    content: bytes = PDF,
    *,
    filename: str = "resume.pdf",
    media_type: str = "application/pdf",
) -> Any:
    return context.client.post(
        "/api/v1/cvs",
        files={"file": (filename, content, media_type)},
    )


def cv_rows(database_url: PostgresDsn) -> list[dict[str, object]]:
    engine = create_engine(str(database_url))
    with engine.connect() as connection:
        rows = [dict(row) for row in connection.execute(text("SELECT * FROM cvs")).mappings()]
    engine.dispose()
    return rows


def test_an_authenticated_upload_stores_the_object_and_owned_metadata(
    cv_client: CVClient,
) -> None:
    owner_id = sign_in(cv_client)

    response = upload(cv_client)

    assert response.status_code == 201
    assert set(response.json()) == {
        "id",
        "media_type",
        "size_bytes",
        "processing_state",
        "created_at",
    }
    assert response.json()["media_type"] == "application/pdf"
    assert response.json()["size_bytes"] == len(PDF)
    assert response.json()["processing_state"] == "pending"
    assert cv_client.storage.writes[0][0] == owner_id
    storage_key = cv_client.storage.writes[0][1]
    assert cv_client.storage.objects[storage_key] == PDF

    row = cv_rows(cv_client.database_url)[0]
    assert row["owner_id"] == owner_id
    assert row["storage_key"] == storage_key
    assert row["checksum_sha256"] == hashlib.sha256(PDF).hexdigest()


def test_an_unauthenticated_upload_cannot_reach_storage(cv_client: CVClient) -> None:
    response = upload(cv_client)

    assert response.status_code == 401
    assert cv_client.storage.writes == []
    assert cv_rows(cv_client.database_url) == []


def test_the_exact_size_limit_is_accepted_and_one_byte_more_is_not(
    cv_client: CVClient,
) -> None:
    sign_in(cv_client)
    exact = b"%PDF-" + b"x" * 11

    assert upload(cv_client, exact).status_code == 201
    over = upload(cv_client, exact + b"private")

    assert over.status_code == 413
    assert over.json()["detail"]["code"] == "file_too_large"
    assert "private" not in over.text
    assert len(cv_client.storage.writes) == 1


@pytest.mark.parametrize(
    ("filename", "media_type", "content", "expected_status", "expected_code"),
    [
        ("resume.pdf", "application/pdf", b"not a PDF", 415, "unsupported_content"),
        ("resume.pdf", "text/plain", PDF, 415, "unsupported_media_type"),
        ("../private.pdf", "application/pdf", PDF, 400, "invalid_filename"),
        ("resume.exe", "application/pdf", PDF, 400, "invalid_filename"),
        ("resume.pdf", "application/pdf", b"", 400, "empty_file"),
    ],
)
def test_hostile_upload_metadata_and_content_are_rejected_without_persistence(
    cv_client: CVClient,
    filename: str,
    media_type: str,
    content: bytes,
    expected_status: int,
    expected_code: str,
) -> None:
    sign_in(cv_client)

    response = upload(cv_client, content, filename=filename, media_type=media_type)

    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == expected_code
    assert filename not in response.text
    if content:
        assert content.decode(errors="ignore") not in response.text
    assert cv_client.storage.writes == []
    assert cv_rows(cv_client.database_url) == []


def test_a_storage_failure_creates_no_metadata_and_exposes_no_details(
    cv_client: CVClient,
) -> None:
    sign_in(cv_client)
    cv_client.storage.fail_write = True

    response = upload(cv_client)

    assert response.status_code == 503
    assert "storage unavailable" not in response.text
    assert cv_rows(cv_client.database_url) == []


def test_the_storage_boundary_cannot_bypass_the_size_response(cv_client: CVClient) -> None:
    sign_in(cv_client)
    cv_client.storage.fail_too_large = True

    response = upload(cv_client)

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "file_too_large"
    assert "private storage detail" not in response.text
    assert cv_rows(cv_client.database_url) == []


def test_a_database_failure_rolls_back_and_deletes_the_object(
    cv_client: CVClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(cv_client)

    async def refuse_commit(_session: AsyncSession) -> None:
        raise SQLAlchemyError("private database detail")

    monkeypatch.setattr(AsyncSession, "commit", refuse_commit)
    response = upload(cv_client)

    assert response.status_code == 503
    assert "private database detail" not in response.text
    assert len(cv_client.storage.deleted) == 1
    assert cv_client.storage.objects == {}
    assert cv_rows(cv_client.database_url) == []


def test_a_cleanup_failure_does_not_expose_storage_details(
    cv_client: CVClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(cv_client)
    cv_client.storage.fail_delete = True

    async def refuse_commit(_session: AsyncSession) -> None:
        raise SQLAlchemyError("private database detail")

    monkeypatch.setattr(AsyncSession, "commit", refuse_commit)
    response = upload(cv_client)

    assert response.status_code == 503
    assert "delete unavailable" not in response.text
    assert len(cv_client.storage.deleted) == 1
    assert cv_rows(cv_client.database_url) == []


@dataclass
class SpoolCloses:
    """How the upload spool was closed, and whether the loop was blocked."""

    on_the_event_loop: int = 0
    off_the_event_loop: int = 0

    @property
    def total(self) -> int:
        return self.on_the_event_loop + self.off_the_event_loop


def record_spool_closes(monkeypatch: pytest.MonkeyPatch) -> SpoolCloses:
    """Swap in a spool that reports which thread closed it.

    A spool past its threshold holds a real file, so closing it flushes and
    unlinks on disk. `asyncio.get_running_loop()` raises in a worker thread and
    succeeds on the loop, which tells the two apart without naming threads.
    """
    closes = SpoolCloses()

    class RecordingSpool(SpooledTemporaryFile[bytes]):
        def close(self) -> None:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                closes.off_the_event_loop += 1
            else:
                closes.on_the_event_loop += 1
            super().close()

    monkeypatch.setattr(service, "SpooledTemporaryFile", RecordingSpool)
    return closes


def test_an_accepted_upload_closes_its_spool_off_the_event_loop(
    cv_client: CVClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(cv_client)
    closes = record_spool_closes(monkeypatch)

    assert upload(cv_client).status_code == 201
    assert closes.total == 1
    assert closes.on_the_event_loop == 0


def test_a_rejected_upload_closes_its_spool_off_the_event_loop(
    cv_client: CVClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(cv_client)
    closes = record_spool_closes(monkeypatch)

    assert upload(cv_client, b"not a pdf").status_code == 415
    assert closes.total == 1
    assert closes.on_the_event_loop == 0


def test_a_failed_upload_closes_its_spool_off_the_event_loop(
    cv_client: CVClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(cv_client)
    closes = record_spool_closes(monkeypatch)

    async def refuse_commit(_session: AsyncSession) -> None:
        raise SQLAlchemyError("private database detail")

    monkeypatch.setattr(AsyncSession, "commit", refuse_commit)

    assert upload(cv_client).status_code == 503
    assert closes.total == 1
    assert closes.on_the_event_loop == 0

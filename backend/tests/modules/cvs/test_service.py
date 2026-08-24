import asyncio
from io import BytesIO

import pytest

from app.modules.cvs import service


class EndlessUpload:
    filename: str | None = "resume.pdf"
    content_type: str | None = "application/pdf"

    def __init__(self) -> None:
        self.requested: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        self.requested.append(size)
        return b"x" * size

    async def close(self) -> None:
        pass


def test_upload_copy_stops_after_the_limit_plus_one_byte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "UPLOAD_CHUNK_BYTES", 4)
    upload = EndlessUpload()
    target = BytesIO()

    size_bytes, initial_bytes = asyncio.run(
        service.copy_upload_bounded(upload, target, max_bytes=10)
    )

    assert size_bytes == 11
    assert len(target.getvalue()) == 11
    assert upload.requested == [4, 4, 3]
    assert initial_bytes == b"xxxxx"

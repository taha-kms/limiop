"""Global state every Adzuna test would otherwise leave behind.

Building an `AdzunaClient`, or resolving credentials through `require`,
installs the process-wide log redaction and registers the key. Both are meant
to stay for the life of a real process, so every test here starts from an
empty secret registry and puts the installation back the way it found it.
"""

from collections.abc import Iterator

import pytest

from job_ingestion import logging_support
from tests.support.logs import preserving_secret_filter


@pytest.fixture(autouse=True)
def _isolated_secret_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(logging_support, "_registered_secrets", set())
    with preserving_secret_filter():
        yield

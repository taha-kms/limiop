"""Global state every Adzuna test would otherwise leave behind.

Building an `AdzunaClient`, or resolving credentials through `require`,
installs the process-wide log redaction and registers the key. Both are meant
to stay for the life of a real process, so every test here starts from an
empty secret registry and puts the installation back the way it found it.
"""

from collections.abc import Iterator
from datetime import date

import pytest

from job_ingestion import logging_support, quota
from tests.support.logs import preserving_secret_filter

FROZEN_DAY = date(2026, 9, 15)


@pytest.fixture(autouse=True)
def _isolated_secret_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(logging_support, "_registered_secrets", set())
    with preserving_secret_filter():
        yield


@pytest.fixture(autouse=True)
def _frozen_quota_day(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the ledger's notion of today for a whole test.

    A test that pre-spends the budget and then lets the client reserve reads
    the clock twice; a UTC midnight between the two would put the spending
    on yesterday's row and the reservation on a fresh one, and the refusal
    the test expects would never come.
    """
    monkeypatch.setattr(quota, "_today", lambda today: today or FROZEN_DAY)

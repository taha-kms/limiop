"""Resolving source credentials from the environment."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime

import pytest
from platform_db.models import IngestionRun
from pydantic import PostgresDsn
from sqlalchemy import delete, select

from job_ingestion import credentials, logging_support
from job_ingestion.contracts import IngestionSummary
from job_ingestion.credentials import Credential, Unconfigured, require, resolve
from job_ingestion.database import Database

APP_ID = Credential(env="SKILLSYNC_FAKE_APP_ID", secret=False)
APP_KEY = Credential(env="SKILLSYNC_FAKE_APP_KEY")


def test_every_variable_present_resolves_to_a_mapping_keyed_by_env_name() -> None:
    resolved = resolve(
        (APP_ID, APP_KEY),
        environ={"SKILLSYNC_FAKE_APP_ID": "id-1", "SKILLSYNC_FAKE_APP_KEY": "key-1"},
    )

    assert resolved == {"SKILLSYNC_FAKE_APP_ID": "id-1", "SKILLSYNC_FAKE_APP_KEY": "key-1"}


def test_values_are_stripped() -> None:
    resolved = resolve((APP_ID,), environ={"SKILLSYNC_FAKE_APP_ID": "  id-1  "})

    assert resolved == {"SKILLSYNC_FAKE_APP_ID": "id-1"}


def test_one_missing_variable_names_only_that_variable() -> None:
    resolved = resolve(
        (APP_ID, APP_KEY),
        environ={"SKILLSYNC_FAKE_APP_ID": "id-1"},
    )

    assert isinstance(resolved, Unconfigured)
    assert resolved.missing == ("SKILLSYNC_FAKE_APP_KEY",)


def test_a_blank_value_counts_as_missing() -> None:
    resolved = resolve(
        (APP_ID,),
        environ={"SKILLSYNC_FAKE_APP_ID": "   "},
    )

    assert isinstance(resolved, Unconfigured)
    assert resolved.missing == ("SKILLSYNC_FAKE_APP_ID",)


def test_an_absent_variable_counts_as_missing() -> None:
    resolved = resolve((APP_ID,), environ={})

    assert isinstance(resolved, Unconfigured)
    assert resolved.missing == ("SKILLSYNC_FAKE_APP_ID",)


def test_a_non_secret_credential_is_still_required() -> None:
    resolved = resolve((APP_ID,), environ={})

    assert isinstance(resolved, Unconfigured)
    assert resolved.missing == ("SKILLSYNC_FAKE_APP_ID",)


def test_unconfigured_reason_names_the_missing_variables() -> None:
    unconfigured = Unconfigured(missing=("SKILLSYNC_FAKE_APP_ID", "SKILLSYNC_FAKE_APP_KEY"))

    assert unconfigured.reason == (
        "source unconfigured: SKILLSYNC_FAKE_APP_ID, SKILLSYNC_FAKE_APP_KEY"
    )


def test_resolve_reads_os_environ_when_none_is_given(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLSYNC_FAKE_APP_ID", "id-from-os-environ")

    resolved = resolve((APP_ID,))

    assert resolved == {"SKILLSYNC_FAKE_APP_ID": "id-from-os-environ"}


def test_require_returns_the_resolved_mapping_when_everything_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SKILLSYNC_FAKE_APP_ID", "id-1")

    async def test() -> None:
        resolved = await require(
            _unreachable_database(),
            "fake",
            (APP_ID,),
            started_at=datetime.now(UTC),
        )

        assert resolved == {"SKILLSYNC_FAKE_APP_ID": "id-1"}

    asyncio.run(test())


def test_require_registers_a_resolved_secret_value_for_redaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(logging_support, "_registered_secrets", set())
    monkeypatch.setenv("SKILLSYNC_FAKE_APP_ID", "id-not-secret-value")
    monkeypatch.setenv("SKILLSYNC_FAKE_APP_KEY", "key-is-a-secret-value")
    # `require` installs the real filter as a side effect (see the test
    # below). This test does not force `_installed` back to `False`, so it
    # triggers at most the one legitimate, idempotent installation the rest of
    # the suite already depends on staying in place -- but if it is the first
    # test in the process to reach that point, it is also the first to touch
    # process-global logging state, so the factory and the root logger's
    # filters are snapshotted and restored to leave no trace either way.
    original_factory = logging.getLogRecordFactory()
    original_root_filters = list(logging.getLogger().filters)

    async def test() -> None:
        resolved = await require(
            _unreachable_database(),
            "fake",
            (APP_ID, APP_KEY),
            started_at=datetime.now(UTC),
        )
        assert resolved == {
            "SKILLSYNC_FAKE_APP_ID": "id-not-secret-value",
            "SKILLSYNC_FAKE_APP_KEY": "key-is-a-secret-value",
        }

    try:
        asyncio.run(test())

        assert "key-is-a-secret-value" in logging_support._registered_secrets
        assert "id-not-secret-value" not in logging_support._registered_secrets
    finally:
        logging.setLogRecordFactory(original_factory)
        logging.getLogger().filters = original_root_filters


def test_require_installs_the_secret_filter_before_registering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`require` must install redaction before any secret value exists in the
    registry, so there is no window where a value is registered but nothing
    is watching for it yet.

    Proved independently of process-global state -- which test ran first,
    whether the filter happens to be installed already from elsewhere -- by
    replacing both calls with recording stubs and checking call count and
    order, rather than an end-to-end log assertion: an earlier version of
    this test asserted a fresh logger's output came out redacted, which
    stayed green even with `install_secret_filter` stubbed to a no-op,
    because an unrelated test defined above it had already installed the real
    filter for the process. The end-to-end proof that redaction actually
    works when installed explicitly lives in `test_logging_support.py`; this
    test proves only that `require` is the one calling `install_secret_filter`,
    exactly once, before it registers anything.
    """
    call_order: list[str] = []

    def fake_install() -> None:
        call_order.append("install")

    def fake_register(values: Iterable[str]) -> None:
        call_order.append("register")
        list(values)  # the real function is a generator consumer; mirror that

    monkeypatch.setattr(credentials, "install_secret_filter", fake_install)
    monkeypatch.setattr(credentials, "register_secrets", fake_register)
    monkeypatch.setenv("SKILLSYNC_FAKE_APP_KEY", "irrelevant-to-this-test")

    async def test() -> None:
        resolved = await require(
            _unreachable_database(),
            "fake",
            (APP_KEY,),
            started_at=datetime.now(UTC),
        )
        assert resolved == {"SKILLSYNC_FAKE_APP_KEY": "irrelevant-to-this-test"}

    asyncio.run(test())

    assert call_order == ["install", "register"]


def _unreachable_database() -> Database:
    # Never touched when every credential is present: `require` must resolve
    # before it goes anywhere near a database.
    return Database(PostgresDsn("postgresql+psycopg://nobody:nobody@127.0.0.1:1/nothing"))


SOURCE = "fake-keyed-source"


def run_database_test(
    database_url: PostgresDsn,
    test: Callable[[Database], Awaitable[None]],
) -> None:
    async def clear(database: Database) -> None:
        async with database.session() as session:
            await session.execute(delete(IngestionRun).where(IngestionRun.source_key == SOURCE))
            await session.commit()

    async def go() -> None:
        database = Database(database_url)
        try:
            await clear(database)
            await test(database)
        finally:
            await clear(database)
            await database.dispose()

    asyncio.run(go())


async def stored(database: Database) -> IngestionRun:
    async with database.session() as session:
        return (
            await session.scalars(select(IngestionRun).where(IngestionRun.source_key == SOURCE))
        ).one()


@pytest.mark.integration
def test_require_records_a_run_and_returns_a_summary_when_a_variable_is_missing(
    database_url: PostgresDsn,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SKILLSYNC_FAKE_APP_ID", "id-1")
    monkeypatch.delenv("SKILLSYNC_FAKE_APP_KEY", raising=False)

    async def test(database: Database) -> None:
        result = await require(
            database,
            SOURCE,
            (APP_ID, APP_KEY),
            started_at=datetime.now(UTC),
        )

        assert isinstance(result, IngestionSummary)
        assert result.fetched == 0
        assert result.processing_complete is False

        row = await stored(database)
        assert row.failed == 1
        assert row.failure_summary == {
            "total": 1,
            "by_stage": {"fetch": 1},
            "reasons": ["source unconfigured: SKILLSYNC_FAKE_APP_KEY"],
        }

    run_database_test(database_url, test)

"""Resolving source credentials from the environment."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from platform_db.models import IngestionRun
from pydantic import PostgresDsn
from sqlalchemy import delete, select

from job_ingestion import logging_support
from job_ingestion.contracts import IngestionSummary
from job_ingestion.credentials import Credential, Unconfigured, require, resolve
from job_ingestion.database import Database
from tests.support.logs import capturing_logs

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

    asyncio.run(test())

    assert "key-is-a-secret-value" in logging_support._registered_secrets
    assert "id-not-secret-value" not in logging_support._registered_secrets


def test_require_installs_the_secret_filter_as_a_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`require` installs redaction itself rather than depending on some other
    setup step having run first -- see `logging_support`'s module docstring
    for why that has to be true by construction. Nothing in this test calls
    `install_secret_filter` directly; the only thing that can have installed
    it, by the time a fresh logger's record comes out redacted, is `require`.
    """
    monkeypatch.setattr(logging_support, "_registered_secrets", set())
    monkeypatch.setattr(logging_support, "_installed", False)
    monkeypatch.setenv("SKILLSYNC_FAKE_APP_KEY", "key-installed-by-require-itself")
    # Forcing `_installed` back to False makes `install_secret_filter` redo its
    # setup, which -- unlike the module-level flag -- leaves lasting marks on
    # process-global state `monkeypatch` cannot undo: an extra `SecretFilter`
    # on the root logger, and another link in the factory chain. Both are
    # snapshotted here and restored, so this test cannot leak into any other.
    original_factory = logging.getLogRecordFactory()
    original_root_filters = list(logging.getLogger().filters)

    async def test() -> None:
        resolved = await require(
            _unreachable_database(),
            "fake",
            (APP_KEY,),
            started_at=datetime.now(UTC),
        )
        assert resolved == {"SKILLSYNC_FAKE_APP_KEY": "key-installed-by-require-itself"}

    try:
        asyncio.run(test())

        with capturing_logs("job_ingestion") as messages:
            logging.getLogger("job_ingestion.some_other_module").info(
                "value is %s", "key-installed-by-require-itself"
            )

        assert messages == ["value is [redacted]"]
    finally:
        logging.setLogRecordFactory(original_factory)
        logging.getLogger().filters = original_root_filters


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

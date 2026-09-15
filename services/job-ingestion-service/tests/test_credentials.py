"""Resolving source credentials from the environment."""

import pytest

from job_ingestion.credentials import Credential, Unconfigured, resolve

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

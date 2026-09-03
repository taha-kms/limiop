import pytest

from job_ingestion.boards.registry import PROVIDERS, provider_for


def test_every_provider_has_a_distinct_source_key() -> None:
    keys = [provider.source_key for provider in PROVIDERS]

    assert len(keys) == len(set(keys))


def test_greenhouse_is_registered() -> None:
    assert provider_for("greenhouse").display_name == "Greenhouse"


def test_an_unknown_source_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="no board provider named nope"):
        provider_for("nope")

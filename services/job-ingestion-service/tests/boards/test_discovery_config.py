import pytest

from job_ingestion.boards.discovery_run import DiscoveryConfig


def test_a_budget_below_one_is_refused() -> None:
    with pytest.raises(ValueError, match="budget must be at least 1"):
        DiscoveryConfig(budget=0)


def test_a_negative_politeness_delay_is_refused() -> None:
    with pytest.raises(ValueError, match="politeness_seconds must not be negative"):
        DiscoveryConfig(politeness_seconds=-0.1)


def test_the_defaults_are_accepted() -> None:
    config = DiscoveryConfig()

    assert config.budget == 200
    assert config.politeness_seconds == 0.5

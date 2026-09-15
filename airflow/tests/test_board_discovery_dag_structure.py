"""Structure tests for the discovery DAGs emitted per board provider."""

from datetime import timedelta
from pathlib import Path

import pytest
from airflow.dag_processing.dagbag import DagBag
from airflow.sdk import DAG
from job_ingestion.boards.registry import PROVIDERS

DAGS_DIR = Path(__file__).parents[1] / "dags"
DAG_IDS = [f"{provider.source_key}_discovery" for provider in PROVIDERS]


@pytest.fixture(scope="session")
def dagbag() -> DagBag:
    return DagBag(dag_folder=str(DAGS_DIR))


@pytest.mark.parametrize("dag_id", DAG_IDS)
def test_every_registered_provider_has_a_discovery_dag(dagbag: DagBag, dag_id: str) -> None:
    assert dag_id in dagbag.dags


@pytest.mark.parametrize(("index", "dag_id"), list(enumerate(DAG_IDS)))
def test_each_discovery_dag_runs_daily_off_peak(dagbag: DagBag, index: int, dag_id: str) -> None:
    """Staggered by registry position, so the documented minutes stay true."""
    dag: DAG = dagbag.dags[dag_id]

    assert dag.schedule == f"{(10 + index * 7) % 60} 3 * * *"
    assert dag.catchup is False
    assert dag.max_active_runs == 1
    assert dag.tags == {"discovery", "boards"}


@pytest.mark.parametrize("dag_id", DAG_IDS)
def test_failure_behavior_is_explicit(dagbag: DagBag, dag_id: str) -> None:
    task = dagbag.dags[dag_id].get_task("discover")

    assert task.retries == 1
    assert task.retry_delay == timedelta(minutes=15)
    assert task.execution_timeout == timedelta(minutes=45)


@pytest.mark.parametrize("dag_id", DAG_IDS)
def test_each_dag_stays_a_single_thin_task(dagbag: DagBag, dag_id: str) -> None:
    assert [task.task_id for task in dagbag.dags[dag_id].tasks] == ["discover"]


def test_no_two_providers_start_on_the_same_minute(dagbag: DagBag) -> None:
    schedules = [dagbag.dags[dag_id].schedule for dag_id in DAG_IDS]

    assert len(schedules) == len(set(schedules))


def test_the_factory_delegates_to_reusable_application_code() -> None:
    source = (DAGS_DIR / "board_discovery.py").read_text()

    assert "from job_ingestion.boards.discovery_run import discover_boards" in source
    assert "from job_ingestion.boards.registry import PROVIDERS" in source

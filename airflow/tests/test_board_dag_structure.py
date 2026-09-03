"""Structure tests for the DAGs emitted per tenant-board provider."""

from datetime import timedelta
from pathlib import Path

import pytest
from airflow.dag_processing.dagbag import DagBag
from airflow.sdk import DAG
from job_ingestion.boards.registry import PROVIDERS

DAGS_DIR = Path(__file__).parents[1] / "dags"
DAG_IDS = [f"{provider.source_key}_ingestion" for provider in PROVIDERS]


@pytest.fixture(scope="session")
def dagbag() -> DagBag:
    return DagBag(dag_folder=str(DAGS_DIR), include_examples=False)


@pytest.mark.parametrize("dag_id", DAG_IDS)
def test_every_registered_provider_has_a_dag(dagbag: DagBag, dag_id: str) -> None:
    assert dag_id in dagbag.dags


def test_greenhouse_keeps_its_schedule(dagbag: DagBag) -> None:
    """Migrated, not rescheduled."""
    dag: DAG = dagbag.dags["greenhouse_ingestion"]

    assert dag.schedule == "30 * * * *"
    assert dag.catchup is False
    assert dag.max_active_runs == 1


@pytest.mark.parametrize("dag_id", DAG_IDS)
def test_failure_behavior_is_explicit(dagbag: DagBag, dag_id: str) -> None:
    task = dagbag.dags[dag_id].get_task("ingest")

    assert task.retries == 2
    assert task.retry_delay == timedelta(minutes=5)
    assert task.execution_timeout == timedelta(minutes=15)


@pytest.mark.parametrize("dag_id", DAG_IDS)
def test_each_dag_stays_a_single_thin_task(dagbag: DagBag, dag_id: str) -> None:
    assert [task.task_id for task in dagbag.dags[dag_id].tasks] == ["ingest"]


def test_no_two_providers_start_on_the_same_minute(dagbag: DagBag) -> None:
    schedules = [dagbag.dags[dag_id].schedule for dag_id in DAG_IDS]

    assert len(schedules) == len(set(schedules))


def test_the_factory_delegates_to_reusable_application_code() -> None:
    source = (DAGS_DIR / "board_ingestion.py").read_text()

    assert "from job_ingestion.boards.pipeline import ingest_board_source" in source
    assert "from job_ingestion.boards.registry import PROVIDERS" in source

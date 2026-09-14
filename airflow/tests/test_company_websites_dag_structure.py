"""Structure tests for the company website resolution DAG."""

from datetime import timedelta
from pathlib import Path

import pytest
from airflow.dag_processing.dagbag import DagBag
from airflow.sdk import DAG

DAGS_DIR = Path(__file__).parents[1] / "dags"
DAG_ID = "company_websites"


@pytest.fixture(scope="session")
def dagbag() -> DagBag:
    return DagBag(dag_folder=str(DAGS_DIR), include_examples=False)


def test_the_dag_is_registered(dagbag: DagBag) -> None:
    assert DAG_ID in dagbag.dags


def test_the_dag_runs_daily_before_discovery(dagbag: DagBag) -> None:
    dag: DAG = dagbag.dags[DAG_ID]

    assert dag.schedule == "40 2 * * *"
    assert dag.catchup is False
    assert dag.max_active_runs == 1
    assert dag.tags == {"discovery", "companies"}


def test_failure_behavior_is_explicit(dagbag: DagBag) -> None:
    task = dagbag.dags[DAG_ID].get_task("resolve")

    assert task.retries == 1
    assert task.retry_delay == timedelta(minutes=15)
    assert task.execution_timeout == timedelta(minutes=45)


def test_the_dag_stays_a_single_thin_task(dagbag: DagBag) -> None:
    dag: DAG = dagbag.dags[DAG_ID]

    assert [task.task_id for task in dag.tasks] == ["resolve"]


def test_the_dag_delegates_to_reusable_application_code() -> None:
    source = (DAGS_DIR / "company_websites.py").read_text()

    assert "from job_ingestion.boards.websites import resolve_websites" in source

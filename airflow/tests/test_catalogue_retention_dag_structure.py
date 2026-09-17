"""Structure tests for the catalogue retention DAG."""

from datetime import timedelta
from pathlib import Path

import pytest
from airflow.dag_processing.dagbag import DagBag
from airflow.sdk import DAG
from job_ingestion.retention import DEFAULT_POLICY

DAGS_DIR = Path(__file__).parents[1] / "dags"
DAG_ID = "catalogue_retention"


@pytest.fixture(scope="session")
def dagbag() -> DagBag:
    return DagBag(dag_folder=str(DAGS_DIR))


def test_the_dag_runs_nightly_after_the_ingestion_runs_settle(dagbag: DagBag) -> None:
    dag: DAG = dagbag.dags[DAG_ID]

    assert dag.schedule == "15 3 * * *"
    assert dag.catchup is False
    assert dag.max_active_runs == 1
    assert dag.tags == {"retention", "jobs"}


def test_failure_behavior_is_explicit(dagbag: DagBag) -> None:
    task = dagbag.dags[DAG_ID].get_task("retain")

    assert task.retries == 1
    assert task.retry_delay == timedelta(minutes=15)
    assert task.execution_timeout == timedelta(minutes=45)


def test_the_dag_stays_a_single_thin_task(dagbag: DagBag) -> None:
    assert [task.task_id for task in dagbag.dags[DAG_ID].tasks] == ["retain"]


def test_the_dag_delegates_to_reusable_application_code() -> None:
    source = (DAGS_DIR / "catalogue_retention.py").read_text()

    assert "from job_ingestion.retention import DEFAULT_POLICY, run_retention" in source


def test_the_dag_states_the_grace_period_the_policy_applies(dagbag: DagBag) -> None:
    dag: DAG = dagbag.dags[DAG_ID]

    assert dag.doc_md is not None
    assert f"{DEFAULT_POLICY.grace.days} days" in dag.doc_md

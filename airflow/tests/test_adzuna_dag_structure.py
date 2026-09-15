"""Structure tests that keep the Adzuna DAG file thin and its schedule under the quota.

These load the DAG through Airflow's own DagBag, so an import error here means
the DAG would also fail to load in a real Airflow deployment.
"""

import logging
from datetime import timedelta
from pathlib import Path

import pytest
from airflow.dag_processing.dagbag import DagBag
from airflow.sdk import DAG
from job_ingestion.adzuna.source import (
    DAILY_QUOTA,
    MONTHLY_CEILING,
    PUBLISHED_DAILY_CEILING,
    WEEKLY_CEILING,
)
from job_ingestion.contracts import IngestionStage, IngestionSummary, RecordFailure

DAGS_DIR = Path(__file__).parents[1] / "dags"
DAG_ID = "adzuna_ingestion"
# "40 */12 * * *": every twelve hours.
RUNS_PER_DAY = 2


@pytest.fixture(scope="session")
def dagbag() -> DagBag:
    return DagBag(dag_folder=str(DAGS_DIR))


@pytest.fixture
def dag(dagbag: DagBag) -> DAG:
    assert DAG_ID in dagbag.dags
    loaded: DAG = dagbag.dags[DAG_ID]
    return loaded


def test_the_dag_is_one_thin_task_on_a_four_hourly_schedule(dag: DAG) -> None:
    assert dag.schedule == "40 */12 * * *"
    assert dag.catchup is False
    assert dag.max_active_runs == 1
    assert [task.task_id for task in dag.tasks] == ["ingest"]

    task = dag.get_task("ingest")
    assert task.retries == 2
    assert task.retry_delay == timedelta(minutes=5)
    assert task.execution_timeout == timedelta(minutes=15)


def test_the_dag_delegates_to_reusable_application_code() -> None:
    source = (DAGS_DIR / f"{DAG_ID}.py").read_text()

    assert "from job_ingestion.adzuna import AdzunaConfig, ingest_adzuna" in source


def test_the_schedule_fits_under_every_published_ceiling(dag: DAG) -> None:
    """The ledger counts days, so the daily budget has to be one that also
    fits the week and the month; the schedule then has to fit the budget.
    Asserted against the real config and the three published numbers rather
    than a literal, so changing any one of them re-does the arithmetic."""
    config = dag.get_task("ingest").python_callable.__globals__["CONFIG"]

    assert config.pages_per_country == 3
    assert config.calls_per_run * RUNS_PER_DAY <= DAILY_QUOTA.per_day
    assert DAILY_QUOTA.per_day <= PUBLISHED_DAILY_CEILING
    assert DAILY_QUOTA.per_day * 7 <= WEEKLY_CEILING
    assert DAILY_QUOTA.per_day * 31 <= MONTHLY_CEILING


def test_an_unconfigured_source_is_a_warning_not_a_task_failure(
    dag: DAG, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    ingest = dag.get_task("ingest").python_callable
    reason = "source unconfigured: SKILLSYNC_ADZUNA_APP_KEY"

    async def unconfigured(**_: object) -> IngestionSummary:
        return IngestionSummary(
            source_key="adzuna",
            failures=(RecordFailure(stage=IngestionStage.FETCH, reason=reason),),
        )

    monkeypatch.setitem(ingest.__globals__, "ingest_adzuna", unconfigured)

    with caplog.at_level(logging.WARNING):
        result = ingest()

    assert result["failed"] == 1
    assert result["fetched"] == 0
    assert reason in caplog.text
    assert "WARNING" in caplog.text

"""Scheduled retention of catalogue rows that stopped being listable.

This file is orchestration only. The rule lives in `job_ingestion.retention`
and is reached through one entry point, so it stays testable without Airflow
and Airflow stays free of business logic.

The rule, as the code applies it: a job that is `expired` or `removed`, that
no source still lists, whose last change is older than the policy's grace
period, and that has not already been anonymised is a candidate. A candidate
nothing user-facing references is deleted with its provenance, skills and
mentions; one that the policy's reference probes still find is anonymised and
marked on the job row instead. The pass works in pages, each selected under a
row lock that skips rows an ingestion run holds and committed on its own, so
it neither blocks a run nor trusts a row that run is rewriting. The grace
period is set once, on the policy, and stated in the DAG's documentation from
there. Runs once a night at 03:15, after the discovery DAGs.
"""

import asyncio
from datetime import datetime, timedelta

from airflow.sdk import dag, task
from job_ingestion.retention import DEFAULT_POLICY, run_retention

START_DATE = datetime(2026, 1, 1)
SCHEDULE = "15 3 * * *"
DOCUMENTATION = (
    "Deletes or anonymises catalogue jobs that stopped being listable more than "
    f"{DEFAULT_POLICY.grace.days} days ago, in locked pages committed one at a time."
)


@dag(
    dag_id="catalogue_retention",
    description="Delete or anonymise catalogue rows past the retention grace period",
    doc_md=DOCUMENTATION,
    schedule=SCHEDULE,
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=15),
        "execution_timeout": timedelta(minutes=45),
    },
    tags=["retention", "jobs"],
)
def catalogue_retention() -> None:
    @task
    def retain() -> dict[str, int]:
        """Run one retention pass and publish what it did."""
        result = asyncio.run(run_retention())
        return {
            "examined": result.examined,
            "deleted": result.deleted,
            "anonymised": result.anonymised,
        }

    retain()


catalogue_retention()

"""Scheduled retention of catalogue rows that stopped being listable.

This file is orchestration only. The rule lives in `job_ingestion.retention`
and is reached through one entry point, so it stays testable without Airflow
and Airflow stays free of business logic.

The rule: a job that has not been `active` for longer than the grace period of
30 days is deleted with its provenance, skills and mentions, unless user-facing
data still references it, in which case it is anonymised and kept. Runs once a
night at 03:15, after the discovery DAGs. The pass works in pages, each locked
and committed on its own, so it neither blocks an ingestion run nor trusts a
row that run is rewriting.
"""

import asyncio
from datetime import datetime, timedelta

from airflow.sdk import dag, task
from job_ingestion.retention import run_retention

START_DATE = datetime(2026, 1, 1)
SCHEDULE = "15 3 * * *"


@dag(
    dag_id="catalogue_retention",
    description="Delete or anonymise catalogue rows past the retention grace period",
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

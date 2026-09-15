"""Scheduled Remotive job ingestion.

This file is orchestration only. Fetching, validation, normalization,
deduplication, and persistence live in `job_ingestion` and are called through
one entry point, so the pipeline stays testable without Airflow and Airflow
stays free of business logic.
"""

import asyncio
from datetime import datetime, timedelta

from airflow.sdk import dag, task
from job_ingestion.remotive import ingest_remotive

START_DATE = datetime(2026, 1, 1)
# Four runs a day, the ceiling Remotive's own API notice asks callers to
# stay within.
SCHEDULE = "20 */6 * * *"
# One request returns everything the feed has; the budget bounds what a run
# stores rather than what it can read.
MAX_RECORDS = 1000


@dag(
    dag_id="remotive_ingestion",
    description="Fetch Remotive postings into the canonical job catalog",
    schedule=SCHEDULE,
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
        "execution_timeout": timedelta(minutes=15),
    },
    tags=["ingestion", "jobs"],
)
def remotive_ingestion() -> None:
    @task
    def ingest() -> dict[str, int | str]:
        """Run one bounded ingestion and publish its summary.

        A run that reports failures still succeeds as a task: the records it did
        store are already committed, and the next scheduled run retries the rest.
        Provider outages are expected, not exceptional.
        """
        summary = asyncio.run(ingest_remotive(max_records=MAX_RECORDS))
        return {
            "source_key": summary.source_key,
            "fetched": summary.fetched,
            "created": summary.created,
            "updated": summary.updated,
            "skipped": summary.skipped,
            "failed": summary.failed,
        }

    ingest()


remotive_ingestion()

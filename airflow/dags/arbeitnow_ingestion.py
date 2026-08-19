"""Scheduled Arbeitnow job ingestion.

This file is orchestration only. Fetching, validation, normalization,
deduplication, and persistence live in `app.modules.ingestion` and are called
through one entry point, so the pipeline stays testable without Airflow and
Airflow stays free of business logic.
"""

import asyncio
from datetime import datetime, timedelta

from airflow.sdk import dag, task

from app.modules.ingestion.arbeitnow import ingest_arbeitnow

START_DATE = datetime(2026, 1, 1)
SCHEDULE = "0 * * * *"
MAX_RECORDS = 500


@dag(
    dag_id="arbeitnow_ingestion",
    description="Fetch Arbeitnow postings into the canonical job catalog",
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
def arbeitnow_ingestion() -> None:
    @task
    def ingest() -> dict[str, int | str]:
        """Run one bounded ingestion and publish its summary.

        A run that reports failures still succeeds as a task: the records it did
        store are already committed, and the next scheduled run retries the rest.
        Provider outages are expected, not exceptional.
        """
        summary = asyncio.run(ingest_arbeitnow(max_records=MAX_RECORDS))
        return {
            "source_key": summary.source_key,
            "fetched": summary.fetched,
            "created": summary.created,
            "updated": summary.updated,
            "skipped": summary.skipped,
            "failed": summary.failed,
        }

    ingest()


arbeitnow_ingestion()

"""Scheduled Himalayas job ingestion.

This file is orchestration only. Fetching, validation, normalization,
deduplication, and persistence live in `job_ingestion` and are called through
one entry point, so the pipeline stays testable without Airflow and Airflow
stays free of business logic.
"""

import asyncio
from datetime import datetime, timedelta

from airflow.sdk import dag, task
from job_ingestion.himalayas import ingest_himalayas

START_DATE = datetime(2026, 1, 1)
# Eight runs a day: the feed is large (roughly 100k postings) and cursor-paged,
# so a bounded walk several times a day covers more of it than one huge run.
SCHEDULE = "25 */3 * * *"
MAX_RECORDS = 500


@dag(
    dag_id="himalayas_ingestion",
    description="Fetch Himalayas postings into the canonical job catalog",
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
def himalayas_ingestion() -> None:
    @task
    def ingest() -> dict[str, int | str]:
        """Run one bounded ingestion and publish its summary.

        A run that reports failures still succeeds as a task: the records it did
        store are already committed, and the next scheduled run retries the rest.
        Provider outages are expected, not exceptional.
        """
        summary = asyncio.run(ingest_himalayas(max_records=MAX_RECORDS))
        return {
            "source_key": summary.source_key,
            "fetched": summary.fetched,
            "created": summary.created,
            "updated": summary.updated,
            "skipped": summary.skipped,
            "failed": summary.failed,
        }

    ingest()


himalayas_ingestion()

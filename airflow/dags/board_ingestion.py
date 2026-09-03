"""Scheduled ingestion for every tenant-board provider.

This file is orchestration only. Fetching, validation, normalization,
deduplication, reconciliation, and persistence live in `job_ingestion` and are
called through one entry point, so the pipeline stays testable without Airflow
and Airflow stays free of business logic.

One DAG per registered provider, each on its own minute of the hour so the
runs do not all start together. Greenhouse keeps the minute it had before the
factory existed.
"""

import asyncio
from datetime import datetime, timedelta

from airflow.sdk import DAG, dag, task
from job_ingestion.boards.pipeline import ingest_board_source
from job_ingestion.boards.provider import BoardProvider
from job_ingestion.boards.registry import PROVIDERS

START_DATE = datetime(2026, 1, 1)
MAX_RECORDS = 500
FIRST_MINUTE = 30
MINUTE_STEP = 5


def schedule_for(index: int) -> str:
    return f"{(FIRST_MINUTE + index * MINUTE_STEP) % 60} * * * *"


def board_ingestion(provider: BoardProvider, index: int) -> DAG:
    @dag(
        dag_id=f"{provider.source_key}_ingestion",
        description=f"Fetch {provider.display_name} postings into the canonical job catalog",
        schedule=schedule_for(index),
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
    def ingestion() -> None:
        @task
        def ingest() -> dict[str, int | str]:
            """Run one bounded ingestion and publish its summary.

            A run that reports failures still succeeds as a task: the records
            it did store are already committed, and the next scheduled run
            retries the rest. Provider outages are expected, not exceptional.
            """
            summary = asyncio.run(ingest_board_source(provider, max_records=MAX_RECORDS))
            return {
                "source_key": summary.source_key,
                "fetched": summary.fetched,
                "created": summary.created,
                "updated": summary.updated,
                "skipped": summary.skipped,
                "failed": summary.failed,
            }

        ingest()

    return ingestion()


for index, provider in enumerate(PROVIDERS):
    # Assigned into the module so the DAG processor finds each one by name.
    globals()[f"{provider.source_key}_ingestion"] = board_ingestion(provider, index)

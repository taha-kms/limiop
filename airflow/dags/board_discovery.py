"""Scheduled discovery for every tenant-board provider.

This file is orchestration only. Guessing a candidate board, probing it, and
corroborating or retiring it live in `job_ingestion` and are called through
one entry point, so discovery stays testable without Airflow and Airflow
stays free of business logic.

Discovery gets its own cadence, separate from ingestion: ingestion polls what
discovery has already confirmed exists, so it can run hourly against a known
board, while discovery is a budgeted guess that a company has a board at all
on this provider, so it runs once a day, off-peak, staggered across providers
so they never start together.
"""

import asyncio
from datetime import datetime, timedelta

from airflow.sdk import DAG, dag, task
from job_ingestion.boards.discovery_run import discover_boards
from job_ingestion.boards.provider import BoardProvider
from job_ingestion.boards.registry import PROVIDERS

START_DATE = datetime(2026, 1, 1)
FIRST_MINUTE = 10
MINUTE_STEP = 7


def schedule_for(index: int) -> str:
    return f"{(FIRST_MINUTE + index * MINUTE_STEP) % 60} 3 * * *"


def board_discovery(provider: BoardProvider, index: int) -> DAG:
    @dag(
        dag_id=f"{provider.source_key}_discovery",
        description=f"Discover and verify {provider.display_name} boards for the catalogue",
        schedule=schedule_for(index),
        start_date=START_DATE,
        catchup=False,
        max_active_runs=1,
        default_args={
            "retries": 1,
            "retry_delay": timedelta(minutes=15),
            "execution_timeout": timedelta(minutes=45),
        },
        tags=["discovery", "boards"],
    )
    def discovery() -> None:
        @task
        def discover() -> dict[str, int | str | bool]:
            """Run one bounded discovery pass and publish its summary."""
            summary = asyncio.run(discover_boards(provider))
            return {
                "source_key": summary.source_key,
                "seeded": summary.seeded,
                "probed": summary.probed,
                "confirmed": summary.confirmed,
                "wrong_company": summary.wrong_company,
                "unverifiable": summary.unverifiable,
                "not_found": summary.not_found,
                "unreachable": summary.unreachable,
                "reactivated": summary.reactivated,
                "skipped_nameless": summary.skipped_nameless,
                "unchanged": summary.unchanged,
                "stopped_at_budget": summary.stopped_at_budget,
            }

        discover()

    return discovery()


for index, provider in enumerate(PROVIDERS):
    # Assigned into the module so the DAG processor finds each one by name.
    globals()[f"{provider.source_key}_discovery"] = board_discovery(provider, index)

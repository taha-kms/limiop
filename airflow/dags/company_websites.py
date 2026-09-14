"""Scheduled resolution of company websites for board corroboration.

This file is orchestration only. Reading the catalogue's stored value,
mining a company's own postings for its most-mentioned domain, and falling
back to Wikidata live in `job_ingestion` and are called through one entry
point, so resolution stays testable without Airflow and Airflow stays free
of business logic.

Runs before the discovery DAGs, at 02:40, so a website resolved tonight is
already on the catalogue when tonight's discovery runs try to corroborate a
guessed board against it.
"""

import asyncio
from datetime import datetime, timedelta

from airflow.sdk import dag, task
from job_ingestion.boards.websites import resolve_websites

START_DATE = datetime(2026, 1, 1)
SCHEDULE = "40 2 * * *"


@dag(
    dag_id="company_websites",
    description="Resolve company websites for board corroboration",
    schedule=SCHEDULE,
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=15),
        "execution_timeout": timedelta(minutes=45),
    },
    tags=["discovery", "companies"],
)
def company_websites() -> None:
    @task
    def resolve() -> dict[str, int | str | bool]:
        """Run one bounded website-resolution pass and publish its summary."""
        summary = asyncio.run(resolve_websites())
        flattened = {
            f"resolved_{source}": summary.resolved_by[source] for source in summary.resolved_by
        }
        return {
            "seeded": summary.seeded,
            **flattened,
            "unresolved": summary.unresolved,
            "stopped_at_budget": summary.stopped_at_budget,
        }

    resolve()


company_websites()

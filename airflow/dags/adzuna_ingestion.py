"""Scheduled Adzuna job ingestion.

This file is orchestration only. Fetching, validation, normalization,
deduplication, and persistence live in `job_ingestion` and are called through
one entry point, so the pipeline stays testable without Airflow and Airflow
stays free of business logic.

Adzuna publishes daily, weekly, and monthly ceilings, and the monthly one
binds: the client reserves every call against a daily budget of 80 derived
from it (`job_ingestion.adzuna.source`), so nothing here can exceed any of
the three. What this file decides is whether the schedule fits under that
budget: two runs a day at three pages per country over twelve countries is
36 calls a run and 72 a day, eight under the budget. That headroom does not
absorb a retried run: a retry after a mid-walk failure is a second run's
worth of calls, and the reservation cuts it short at the budget rather than
letting it through. The retried run stores what it fetched before the cut,
and the next scheduled run picks up the rest.

The source stays unconfigured in production until the "Jobs by Adzuna"
attribution ships on the listing (#367): a run without credentials succeeds,
records that nothing was fetched, and warns.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from airflow.sdk import dag, task
from job_ingestion.adzuna import AdzunaConfig, ingest_adzuna
from job_ingestion.credentials import is_unconfigured

logger = logging.getLogger(__name__)

START_DATE = datetime(2026, 1, 1)
# Two runs a day, offset from the other feeds' minutes.
SCHEDULE = "40 */12 * * *"
# Well above what 36 pages of 50 can return, so the page budget, not the
# record budget, is what bounds a run.
MAX_RECORDS = 2000
CONFIG = AdzunaConfig(pages_per_country=3)


@dag(
    dag_id="adzuna_ingestion",
    description="Fetch Adzuna postings into the canonical job catalog within its daily quota",
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
def adzuna_ingestion() -> None:
    @task
    def ingest() -> dict[str, int | str | bool]:
        """Run one bounded ingestion and publish its summary.

        A run that reports failures still succeeds as a task: the records it
        did store are already committed, and the next scheduled run retries
        the rest. A run that stopped at the quota is not a failure either; it
        says so in `stopped_at_budget`. A source with no credentials set is
        worth a warning, since every run until they are set will do nothing.
        """
        summary = asyncio.run(ingest_adzuna(config=CONFIG, max_records=MAX_RECORDS))
        if is_unconfigured(summary):
            logger.warning("adzuna fetched nothing: %s", summary.failures[0].reason)
        return {
            "source_key": summary.source_key,
            "fetched": summary.fetched,
            "created": summary.created,
            "updated": summary.updated,
            "skipped": summary.skipped,
            "failed": summary.failed,
            "stopped_at_budget": summary.stopped_at_budget,
            "reached_the_end": summary.reached_the_end,
        }

    ingest()


adzuna_ingestion()

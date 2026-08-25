# 02 — Schedule Greenhouse independently

## Why
Only Arbeitnow is scheduled. Greenhouse has run on demand because there was
nowhere to schedule it into; the `pipelines` Compose profile removed that
reason.

## Scope
A second DAG, `airflow/dags/greenhouse_ingestion.py`, modelled on
`arbeitnow_ingestion.py` and independent of it.

- Hourly, but not on the same minute. Arbeitnow runs at `0 * * * *`; put
  Greenhouse at `30 * * * *` so two ingestions do not contend for the same
  database and the same provider budget at once.
- Its own `retries`, `retry_delay`, and `execution_timeout`. Independent means
  a Greenhouse failure neither blocks nor retries Arbeitnow, and the reverse.
- `catchup=False` and `max_active_runs=1`, as Arbeitnow has. Overlapping runs
  of the same source would fight over the same rows.
- Call `ingest_greenhouse` from `job_ingestion.greenhouse`. The DAG is
  orchestration only: no fetching, no normalization, no reconciliation logic in
  the DAG file. It publishes the same run summary shape Arbeitnow does.
- A structure test in `airflow/tests/`, matching how the Arbeitnow DAG is
  tested.

## Do not touch the lifecycle rules
`ingest_greenhouse` already folds unreadable boards into its summary, and a run
with a skipped board is processing-complete but not source-exhausted, so it is
not entitled to withdraw postings. That distinction was measured — against a
real board it was the difference between withdrawing twenty-four open jobs and
withdrawing none. Scheduling must not change it.

Per-source retirement already exists: an unseen posting retires that source's
provenance row, and the job is withdrawn only when no un-retired provenance
remains. Two scheduled sources is the case that rule was written for.

## Out of scope
Board discovery — that is #120, and the board list stays as configured.
Changing the Arbeitnow DAG.

## Acceptance
- `docker compose --profile pipelines up --wait`, then `airflow dags list`
  shows both `arbeitnow_ingestion` and `greenhouse_ingestion`, unpaused.
- Triggering `greenhouse_ingestion` completes and writes jobs. Report the run
  summary it published and the job count before and after.
- Triggering it a second time is a no-op for existing postings: the count of
  jobs does not double, and no open job is wrongly withdrawn.
- `cd airflow && pytest` passes.

Note: these need a Docker daemon or a local Airflow. If you have neither, say
precisely which criteria are unverified.

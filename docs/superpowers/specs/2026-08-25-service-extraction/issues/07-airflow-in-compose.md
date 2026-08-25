# 07 — Add Airflow to docker-compose

## Why
`docker-compose.yml` declares `database`, `migrate`, and `api`, and no Airflow
at all. The DAG has nowhere to run locally, which is why only Arbeitnow is
scheduled and why the schedule has never been exercised against a persistent
database. The orchestration story is unfinished rather than wrong, and this
finishes it.

## Scope
- A `Dockerfile` for `airflow/`, installing `apache-airflow` and
  `-e ../services/job-ingestion-service`. It must not install the backend.
- Compose services: `airflow-init` (database migration and admin user),
  `airflow-scheduler`, `airflow-apiserver`. Airflow 3.2 is what
  `airflow/requirements.txt` pins — follow its component names rather than the
  Airflow 2 ones.
- Airflow's own metadata database: a separate database **inside the same
  PostgreSQL instance**, not a second server and not the SkillSync database.
  Airflow's metadata is Airflow's private business and must not share a schema
  with the application tables.
- The DAG needs `SKILLSYNC_DATABASE_URL` pointing at the SkillSync database.
- Put these behind a compose profile (e.g. `--profile pipelines`) so the default
  `docker compose up` stays the fast API-and-database loop it is today.

## Out of scope
Scheduling Greenhouse. Deciding where a persistent environment lives — that is
still an open question in the delivery plan and this issue does not close it.

## Acceptance
- `docker compose --profile pipelines up` brings the scheduler to healthy and
  the DAG appears, unpaused, in the Airflow UI.
- Triggering `arbeitnow_ingestion` writes jobs into the SkillSync database.
- The default `docker compose up` is unchanged in service set and startup time.
- The Airflow image does not contain `fastapi`.

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
  Note the build context: `platform/db` and `services/job-ingestion-service`
  both sit outside `airflow/`, so the context starts at the repository root,
  as the backend image already does.
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
- The Airflow image does not contain `skillsync-backend`, `argon2-cffi`, or
  `pypdf`.

Two earlier versions of this criterion were wrong, so here is the evidence
rather than another guess. Inspecting the published `apache-airflow-core==3.2.2`
wheel metadata:

```text
fastapi    -> fastapi[standard-no-fastapi-cloud-cli]>=0.129
uvicorn    -> uvicorn>=0.37.0
pyjwt      -> pyjwt>=2.11.0
httpx      -> httpx>=0.25.0
sqlalchemy -> sqlalchemy[asyncio]>=2.0.48
argon2     -> NOT A DEPENDENCY
pypdf      -> NOT A DEPENDENCY
```

Airflow's own API server is built on FastAPI and served by uvicorn, and it uses
PyJWT for API authentication, so those cannot be excluded and their presence
says nothing about the boundary. `argon2-cffi` and `pypdf` are the backend's
alone: password hashing and CV text extraction. If either appears in the Airflow
image, the backend leaked in.

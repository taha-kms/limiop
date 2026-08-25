# Service extraction — design

Date: 2026-08-25

## Problem

Ingestion is 2183 of the backend's 6388 application lines, and the backend has
no reason to know how a job posting is fetched. The module boundary under
`backend/app/modules/ingestion` is already sound — per-source
`client`/`records`/`normalizer`/`pipeline`, shared `contracts`,
`deduplication`, `reconciliation`, `persistence`. What has no boundary is the
deployment unit, the dependency set, and schema ownership:

- `airflow/requirements.txt` installs `-e ../backend`, so the Airflow image
  carries FastAPI, uvicorn, argon2, pypdf, and the whole API.
- `airflow/dags/arbeitnow_ingestion.py` imports `app.modules.ingestion.*`.
- `backend/alembic` owns migrations for tables the backend only reads.
- `docker-compose.yml` has no Airflow services at all, so no DAG runs locally.

Nothing prevents the boundary being crossed again except review. The fix is to
make a crossing a build failure.

## Decision

Service-oriented, with the database shared and the schema owned by a package.

- **One PostgreSQL.** Rejected a data-access service: `persistence.py` upserts a
  job, its provenance rows, and retirement state in one transaction, and
  `reconciliation.py` resolves catalog-wide across sources. Both lose
  atomicity or become paginated round-trips behind an API, and every schema
  change would ship three deployables in lockstep. That is a distributed
  monolith with worse coupling than today.
- **`platform/db` is a package, not a service.** Models, migrations, session
  factory. No FastAPI, no HTTP, no query helpers, no business logic. It solves
  the same problem a data-access service would — one owner for the tables — and
  enforces it at import time rather than over a network hop.
- **A table lives with whoever writes it, unless two deployables touch it.**
  Shared: `jobs`, `companies`, `job_sources`, `job_provenance`,
  `skill_concepts`, `skill_surface_forms`, `skill_alias_versions`.
  Backend-private: `users`, `cvs`, `candidate_profiles`,
  `candidate_profile_skills`.
- **Two Alembic chains, one database.** `platform/db` owns the shared tables
  under its own version table; the backend keeps its own for its own. Only one
  foreign key crosses the line — `candidate_profile_skills.skill_concept_id` →
  `skill_concepts` — and it points one way, so the run order is fixed: platform
  first, then backend.
- **`services/job-ingestion-service` is its own deployable.** Own
  `pyproject.toml`, own image, depends on `platform-db`, never on the backend.
  Airflow depends on the ingestion service, not on the API.

## What this does not change

`PROJECT_CONTEXT.md` §20 stays as written. No microservice owns its own
datastore, no message broker is introduced, no second database appears, and
Alembic remains the schema authority. The independence being bought is
independent deployability and an enforced dependency set, neither of which
§20 forbids.

## Target layout

```text
skillsync/
├── platform/
│   └── db/                      # models, migrations, session factory
├── services/
│   └── job-ingestion-service/   # sources, normalize, dedup, persist
├── backend/                     # API only
├── frontend/
├── airflow/                     # orchestration, depends on services/*
└── docs/
```

## Sequence

Ten changes, each leaving the repository green. The chain split (03) is the
only one that touches migration history, and it is deliberately isolated from
the code moves on either side of it. Issue 06 carries the Airflow import repair
with it, because moving the module breaks Airflow the moment it lands.

| # | Change | Risk |
| --- | --- | --- |
| 01 | Scaffold `platform/db` | None |
| 02 | Move shared models into it | Low |
| 03 | Split the Alembic chain | **High** |
| 04 | Compose runs both chains in order | Low |
| 05 | Scaffold `services/job-ingestion-service` | None |
| 06 | Move ingestion code and tests; repoint Airflow | Medium |
| 07 | Add Airflow to docker-compose | Low |
| 08 | Enforce the boundaries in CI | Low |
| 09 | Update the architecture docs | None |
| 10 | Source feasibility gate | None |

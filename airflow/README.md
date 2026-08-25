# SkillSync Airflow

Scheduled orchestration for SkillSync data workflows.

DAGs are thin. Fetching, validation, normalization, deduplication, and
persistence live in `services/job-ingestion-service` and are invoked through a
single entry point, so pipeline behavior is tested under the service's own gates
and Airflow only decides *when* work runs.

## DAGs

| DAG | Schedule | Purpose |
| --- | --- | --- |
| `arbeitnow_ingestion` | hourly | Fetch Arbeitnow postings into the canonical job catalog |

## Local setup

Airflow is intentionally kept out of `backend/`. It pulls a large dependency
set and is never installed into the API image.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Validation

```bash
AIRFLOW__CORE__LOAD_EXAMPLES=False pytest tests
```

The structure test loads every DAG through Airflow's own `DagBag`, so an import
error, a missing schedule, or business logic creeping into a DAG file fails CI.

## Configuration

DAGs read the ingestion service's `SKILLSYNC_` environment variables. The
database URL must be set for a run to do anything:

```bash
export SKILLSYNC_DATABASE_URL=postgresql+psycopg://user:password@host:5432/skillsync
```

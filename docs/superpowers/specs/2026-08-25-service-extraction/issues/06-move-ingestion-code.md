# 06 — Move ingestion into the service

## Why
This is the change the whole sequence exists for: the backend stops containing
the code that fetches and normalizes job postings.

## Scope
Move `backend/app/modules/ingestion/` (17 files, 2183 lines) to
`services/job-ingestion-service/job_ingestion/`, preserving its internal
structure: `contracts.py`, `errors.py`, `pipeline.py`, `deduplication.py`,
`reconciliation.py`, `persistence.py`, and the per-source packages
`arbeitnow/` and `greenhouse/`, each with `client`, `records`, `normalizer`,
`pipeline`.

Also move:
- `backend/tests/modules/ingestion/` to the service's `tests/`.
- `backend/scripts/seed_catalog.py`, which imports
  `app.modules.ingestion.persistence`. It seeds the catalog, so it belongs with
  the catalog writer. If the backend's own tests depend on it, give them a
  fixture instead of a cross-service import.

Then:
- Delete the ingestion module and its tests from the backend. No shim.
- Remove `httpx2` from `backend/pyproject.toml` **if** nothing else in the
  backend imports it. Check before removing.
- Persistence writes through models now imported from `platform_db.models`.

## Also in scope — keep Airflow working

Moving the module breaks `airflow/`, so the repair belongs in the same change
rather than a follow-up that leaves the repository red in between. Three files:

- `airflow/requirements.txt` — replace `-e ../backend` with
  `-e ../services/job-ingestion-service`. This is the line that put FastAPI,
  uvicorn, argon2, and pypdf into the Airflow image.
- `airflow/dags/arbeitnow_ingestion.py:14` — import `ingest_arbeitnow` from
  `job_ingestion.arbeitnow`. Update the module docstring, which names
  `app.modules.ingestion` in prose.
- `airflow/tests/test_dag_structure.py:81` — asserts the import string
  literally. Update the expected string.

## Out of scope
Adding Airflow services to docker-compose — issue 07. Behaviour changes of any
kind: this is a move, and the tests that move with it must pass unmodified
except for their import lines.

## Acceptance
- `grep -rn "modules.ingestion" backend/ airflow/` returns nothing.
- `grep -rn "^from app\.\|^import app\." services/ airflow/` returns nothing.
- The moved test suite passes in its new home with the same coverage gate.
- `cd backend && pytest` passes, and the backend's coverage does not fall below
  its gate now that a third of its lines have left.
- `cd airflow && pytest` passes.
- The Airflow environment no longer resolves `fastapi` or `uvicorn`.

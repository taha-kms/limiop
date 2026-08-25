# 08 — Enforce the boundaries in CI

## Why
Every boundary in this sequence is currently a convention. Conventions are
restored by review, and review is exactly what let the original coupling
accumulate. A crossing should fail a build.

## Scope
Add a CI job that fails on any of these:

| Rule | Why |
| --- | --- |
| `job_ingestion` must not import `app.*` | The service must not depend on the API |
| `app.*` must not import `job_ingestion` | The API must not know how jobs are fetched |
| `platform_db` must not import `app.*` or `job_ingestion` | The schema package sits below both |
| `platform_db` must not import `fastapi`, `starlette`, `uvicorn`, `httpx2` | It is a package, not a service |
| `platform_db` must contain only models, migrations, and the session factory | Stops it drifting into the data-access service that was rejected |

Use `import-linter` with a layered contract if it fits the repository's tooling;
a small `pytest` check that walks the ASTs is an acceptable alternative if it
keeps the failure message specific about which import broke which rule. A bare
`grep` in a shell step is not — it cannot tell an import from a docstring, and
`airflow/dags/arbeitnow_ingestion.py` has already had the module path in prose.

The last rule cannot be checked by imports alone. Express it as an explicit
allowlist of module names under `platform_db`, so adding a new module there is
a deliberate edit to the contract.

## Acceptance
- The job passes on the current tree.
- Adding `from app.core.config import get_settings` to any `job_ingestion`
  module fails it, with a message naming the rule. Prove this locally, then
  revert.
- The job runs on every pull request.

# 05 — Scaffold `services/job-ingestion-service`

## Why
Ingestion needs somewhere to be that is not the backend, with its own
dependency set, before the code moves.

## Scope
Create `services/job-ingestion-service/` as an installable package named
`skillsync-job-ingestion` with import name `job_ingestion`.

- `pyproject.toml` — runtime dependencies: `skillsync-platform-db`, `httpx2`,
  `pydantic`, `sqlalchemy[asyncio]`. **Not** `fastapi`, **not** `uvicorn`,
  **not** `argon2-cffi`, **not** `pypdf`. Dev extra matching the backend's
  tooling pins.
- `job_ingestion/__init__.py`, plus an empty `job_ingestion/config.py` holding
  a settings object for the database URL and per-source configuration, read
  from the environment. It must not import `app.core.config`.
- `ruff.toml`, mypy config, and a `pytest` config with the same
  `--cov-fail-under` gate the backend uses.
- `tests/test_package.py` asserting `job_ingestion` imports and that neither
  `fastapi` nor any `app.*` module is importable from its dependency set.

## Out of scope
Moving any ingestion code — issue 06.

## Acceptance
- `pip install -e services/job-ingestion-service` succeeds.
- `ruff`, `mypy`, and `pytest` clean for the new package.
- The backend and the existing tests are untouched and still pass.

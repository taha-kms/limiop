# 01 — Scaffold the `platform/db` package

## Why
The backend currently defines every table, including the seven that a future
ingestion service also has to write. Before anything moves, there has to be a
package to move it into.

## Scope
Create `platform/db/` as an installable Python package named `skillsync-platform-db`
with import name `platform_db`.

- `platform/db/pyproject.toml` — setuptools build, `requires-python >=3.12,<3.14`.
  Runtime dependencies: `sqlalchemy[asyncio]`, `alembic`, `psycopg[binary]`.
  Pin ranges the same way `backend/pyproject.toml` does.
  Dev extra: `mypy`, `pytest`, `ruff`, matching the backend's pins.
- `platform/db/platform_db/__init__.py`
- `platform/db/platform_db/base.py` — the declarative `Base`, moved in shape
  from `backend/app/db/base.py`. Read that file first and keep its conventions
  (naming convention, type annotation map, whatever it declares).
- `platform/db/platform_db/session.py` — engine and session factory, taking the
  database URL as an argument rather than importing a settings object.
  `backend/app/db/session.py` is the reference; the difference is that this one
  must not depend on `app.core.config`.
- `platform/db/ruff.toml` and mypy config mirroring the backend's settings.
- `platform/db/tests/test_package.py` — asserts `platform_db.base.Base` imports
  and that `platform_db` does not import FastAPI or the backend.

## Out of scope
Moving any model. Touching the backend. Touching Alembic. The backend keeps
working exactly as it does today.

## Constraints
- `platform_db` must never import `fastapi`, `starlette`, `uvicorn`, `httpx2`,
  or anything under `app.*`. This is the entire point of the package.
- No query helpers, no repository classes, no business logic. Models,
  migrations, session factory only.

## Acceptance
- `pip install -e platform/db` succeeds in a clean environment.
- `python -c "from platform_db.base import Base"` works.
- `ruff check platform/db && ruff format --check platform/db` clean.
- `mypy platform/db` clean.
- `pytest platform/db/tests` passes.
- `cd backend && pytest` still passes unchanged.

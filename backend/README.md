# SkillSync Backend

The backend is a FastAPI application organized around explicit HTTP, configuration, and schema boundaries. Database and business-service layers will be introduced when their first concrete features are implemented.

## Requirements

- Python 3.12
- PostgreSQL 17 for database-backed development
- Docker and Docker Compose for the containerized workflow

## Native setup

Run these commands from `backend/`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
cp .env.example .env
```

Start the development server:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

The health endpoint is available at `GET /health`. Interactive API documentation is available at `/docs` while the application is running.

## Configuration

Configuration uses environment variables with the `SKILLSYNC_` prefix. Local values may be placed in `backend/.env`, which is ignored by Git.

| Variable | Default | Purpose |
| --- | --- | --- |
| `SKILLSYNC_APP_NAME` | `SkillSync API` | API title exposed in OpenAPI |
| `SKILLSYNC_ENVIRONMENT` | `local` | Runtime environment: `local`, `test`, `staging`, or `production` |
| `SKILLSYNC_DEBUG` | `false` | Enables FastAPI debug behavior |
| `SKILLSYNC_DATABASE_URL` | `postgresql+psycopg://localhost/skillsync` | Async-capable PostgreSQL connection URL |
| `SKILLSYNC_CV_MAX_UPLOAD_BYTES` | `5242880` | Maximum accepted CV file size in bytes |
| `SKILLSYNC_CV_ALLOWED_FORMATS` | `["pdf"]` | JSON list of enabled CV formats; currently only `pdf` is supported |
| `SKILLSYNC_CV_STORAGE_ROOT` | `uploads/cvs` | Private local-development directory for CV objects |

The default database URL is a credential-free local development placeholder. Override it in `.env` to match your PostgreSQL authentication setup. URL-encode special characters in credentials.

The filesystem CV backend is for local development. It writes with private
directory permissions and atomic publication. The container directory is not a
durable volume, so set a different private directory or mount one when local CVs
must survive a container replacement. A production object-storage backend is
intentionally not part of the current implementation.

## Docker Compose

From the repository root:

```bash
cp .env.example .env
docker compose up --build
```

Replace the example database password and matching URL before starting the services. Compose starts PostgreSQL, waits for it to become healthy, applies Alembic migrations, and then starts the API at `http://localhost:8000`.

Stop the services while keeping database data:

```bash
docker compose down
```

Passing `--volumes` also deletes the local PostgreSQL data volume.

## Migrations

Run Alembic commands from `backend/` with `SKILLSYNC_DATABASE_URL` configured:

```bash
alembic upgrade head
alembic downgrade base
alembic current
```

Alembic and the application share the metadata in `app/db/base.py`. Persistent schema changes must update both the SQLAlchemy model and the migration history.

## Job catalog

The job catalog lives in `app/modules/jobs/` and owns the source-independent job
representation shared by ingestion, the API, analytics, and matching. Its fields,
validation rules, and provenance model are described in
[the canonical job contract](../docs/canonical-job-contract.md).

## Validation

```bash
ruff format --check .
ruff check .
mypy
pytest
```

Set `SKILLSYNC_TEST_DATABASE_URL` to include PostgreSQL session and migration integration tests. Without it, those tests are reported as skipped. Pytest enforces branch-aware coverage and writes `coverage.xml` for Codecov and quality analysis.

## Structure

```text
backend/
├── app/
│   ├── api/          # Route registration and HTTP endpoints
│   ├── core/         # Typed application configuration
│   ├── db/           # SQLAlchemy engine, sessions, and shared metadata
│   ├── modules/      # Bounded domain modules with their own models and schemas
│   ├── schemas/      # Public API contracts
│   └── main.py       # Application factory and ASGI entry point
├── alembic/          # Versioned PostgreSQL migrations
├── tests/            # API and configuration tests
└── pyproject.toml    # Package, test, lint, and type-check configuration
```

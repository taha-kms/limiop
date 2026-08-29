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
python -m pip install -e ../platform/db -e '.[dev]'
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
| `SKILLSYNC_CV_PDF_MAX_PAGES` | `20` | Maximum pages the PDF parser will inspect |
| `SKILLSYNC_CV_PDF_MAX_TEXT_CHARACTERS` | `100000` | Maximum normalized characters returned from one CV |
| `SKILLSYNC_CV_PDF_TIMEOUT_SECONDS` | `5` | Hard subprocess deadline for PDF parsing |

The default database URL is a credential-free local development placeholder. Override it in `.env` to match your PostgreSQL authentication setup. URL-encode special characters in credentials.

The filesystem CV backend is for local development. It writes with private
directory permissions and atomic publication. The container directory is not a
durable volume, so set a different private directory or mount one when local CVs
must survive a container replacement. A production object-storage backend is
intentionally not part of the current implementation.

## CV intake

`POST /api/v1/cvs` accepts one authenticated multipart field named `file`.
Version one accepts a PDF within the configured size limit and returns only the
new record's public metadata; storage keys and checksums stay internal. The
boundary and retention rules are documented in the
[CV upload policy](../docs/cv-upload-policy.md).

PDF text extraction runs in a disposable subprocess with file, page, output,
and time limits. It returns normalized plain text only. Skill extraction and
candidate-profile updates are separate downstream work.

## Docker Compose

From the repository root:

```bash
cp .env.example .env
docker volume create skillsync_postgres_data
docker compose up --build
```

Replace the example database password and matching URL before starting the services. The external PostgreSQL volume only needs to be created once. If `SKILLSYNC_POSTGRES_VOLUME` is changed in `.env`, create a volume with that exact name instead. Compose starts PostgreSQL, waits for it to become healthy, applies Alembic migrations, and then starts the API at `http://localhost:8000`.

Stop the services while keeping database data:

```bash
docker compose down
```

The external PostgreSQL volume survives `docker compose down -v`, preserving both the job catalogue and the Airflow metadata database with its DAG history and run state. To reset PostgreSQL deliberately, remove the configured volume by name, recreate it, and start the stack so the migrations build an empty database:

```bash
docker compose down -v
docker volume rm skillsync_postgres_data
docker volume create skillsync_postgres_data
docker compose up --build
```

Use the configured volume name in both volume commands when overriding `SKILLSYNC_POSTGRES_VOLUME`.

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

## Alias tables

After applying the database migrations, load a published known-skill vocabulary
from `backend/` with:

```bash
python -m scripts.load_alias_table --vocabulary-version 2026.08.29.2
```

The command uses `SKILLSYNC_DATABASE_URL`. Repeating the same version is a
no-op when the stored rows match the artifact; it fails instead of changing an
already-published version when their contents differ.

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

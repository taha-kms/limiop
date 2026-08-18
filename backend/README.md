# SkillSync Backend

The backend is a FastAPI application organized around explicit HTTP, configuration, and schema boundaries. Database and business-service layers will be introduced when their first concrete features are implemented.

## Requirements

- Python 3.12

## Setup

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

## Validation

```bash
ruff format --check .
ruff check .
mypy
pytest
```

Pytest enforces branch-aware coverage and writes `coverage.xml` for Codecov and quality analysis.

## Structure

```text
backend/
├── app/
│   ├── api/          # Route registration and HTTP endpoints
│   ├── core/         # Typed application configuration
│   ├── schemas/      # Public API contracts
│   └── main.py       # Application factory and ASGI entry point
├── tests/            # API and configuration tests
└── pyproject.toml    # Package, test, lint, and type-check configuration
```

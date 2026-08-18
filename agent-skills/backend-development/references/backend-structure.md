# Backend Structure

Use the existing repository layout if it is already established. When creating the initial backend structure, prefer a simple layout like:

```text
backend/
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── dependencies.py
│   │   └── routes/
│   ├── core/
│   │   ├── config.py
│   │   └── security.py
│   ├── db/
│   │   ├── base.py
│   │   └── session.py
│   ├── models/
│   ├── schemas/
│   ├── services/
│   ├── clients/
│   └── exceptions/
├── alembic/
├── tests/
└── pyproject.toml
```

Do not force this exact tree onto an existing codebase. Preserve established conventions unless there is an issue specifically for restructuring.

## Placement Guide

Use `api/routes/` for HTTP endpoints and route registration.

Use `api/dependencies.py` or focused dependency modules for request-scoped dependencies such as the current user or database session.

Use `core/` for cross-cutting configuration/security primitives. Do not turn it into a miscellaneous dumping ground.

Use `db/` for engine/session/base setup and database infrastructure.

Use `models/` for SQLAlchemy models.

Use `schemas/` for Pydantic request/response contracts.

Use `services/` for application behavior that is reusable outside a single route.

Use `clients/` for backend-owned calls to external services.

Keep Airflow DAGs and ML training code outside `backend/` unless the repository has deliberately established a shared package for reusable code.

## Dependency Direction

Prefer dependencies to flow inward:

```text
route -> service -> model/database
            |
            -> client/inference interface
```

Avoid:

```text
model -> route
service -> FastAPI request object
frontend -> database
Airflow DAG -> FastAPI route as internal business API when a reusable module is available
```

A service may use SQLAlchemy directly when a separate repository abstraction would add ceremony without value.

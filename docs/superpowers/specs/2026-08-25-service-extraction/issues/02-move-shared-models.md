# 02 — Move the shared models into `platform/db`

## Why
Seven tables are written by ingestion or read by two deployables. They cannot
live inside the backend once ingestion is its own service.

## Scope
Move these model definitions out of the backend and into
`platform/db/platform_db/models/`:

| Table | Currently in |
| --- | --- |
| `jobs`, `companies`, `job_sources`, `job_provenance` | `backend/app/modules/jobs/models.py` |
| `skill_concepts`, `skill_surface_forms`, `skill_alias_versions` | `backend/app/modules/skills/models.py` |

Leave these in the backend, unchanged: `users`, `cvs`, `candidate_profiles`,
`candidate_profile_skills`.

- Group them as `platform_db/models/catalog.py` (the four job tables) and
  `platform_db/models/skills.py` (the three skill tables), re-exported from
  `platform_db/models/__init__.py`.
- The backend's own models continue to inherit from the same `Base`, now
  imported from `platform_db.base`. One `MetaData` across both packages — the
  cross-package foreign key `candidate_profile_skills.skill_concept_id` →
  `skill_concepts.id` requires it.
- Update every import in `backend/` and `backend/tests/` to the new path.
  Do not leave re-export shims in `app.modules.jobs.models` or
  `app.modules.skills.models`; the point is that the dependency is visible.
- `backend/pyproject.toml` gains `skillsync-platform-db` as a dependency.
  Install it from the local path for development.
- **The Docker build context has to move.** `docker-compose.yml` builds the API
  with `context: ./backend`, so `platform/` sits outside it and
  `docker compose build api` fails the moment the backend depends on a local
  path package. Change the context to the repository root with an explicit
  `dockerfile: backend/Dockerfile`, and adjust the paths inside that Dockerfile
  accordingly. Without this the image cannot be built and issue 04 cannot pass.
- `backend/alembic/env.py` imports the moved models from `platform_db.models`
  so autogenerate still sees the full metadata.

## Out of scope
Splitting the Alembic chain — that is issue 03. Moving ingestion code — that is
issue 06. Any schema change at all.

## Acceptance
- No schema change: `alembic revision --autogenerate` produces an **empty**
  migration. Verify this and then delete the generated file. If it is not
  empty, the move altered a model and must be corrected rather than migrated.
- `grep -rn "app.modules.jobs.models\|app.modules.skills.models" backend airflow`
  returns nothing outside the deleted files.
- `cd backend && pytest` passes, coverage gate included.
- `docker compose build api` succeeds.
- `ruff check`, `ruff format --check`, and `mypy` clean on both packages.

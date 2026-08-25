# 04 — Run both migration chains in docker-compose

## Why
`docker-compose.yml` has one `migrate` service running the backend chain. There
are now two chains, and one ordering constraint between them.

## Scope
- Replace `migrate` with `migrate-platform` and `migrate-backend`.
- `migrate-platform` depends on `database` being healthy.
- `migrate-backend` depends on `migrate-platform` completing successfully.
- `api` depends on `migrate-backend` completing successfully.
- The order is not a preference: `candidate_profile_skills.skill_concept_id`
  references `skill_concepts`, so the platform tables must exist first.
- `migrate-platform` needs an image containing `platform/db`. Either build a
  small image for the package or reuse the backend image, which already depends
  on it — pick one and say why in the compose file comments.

## Out of scope
Airflow services — issue 08.

## Acceptance
- `docker compose up` from a clean volume brings the API to healthy.
- `docker compose down -v && docker compose up` repeats it.
- Both `alembic_version` and `alembic_version_platform` exist and are at head.

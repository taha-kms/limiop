# 04 — Run both migration chains in docker-compose

## Urgency

`main` is currently red because of exactly this gap. #162 split the chain and
landed without this issue, so every consumer that runs only the backend chain
now fails with `relation "skill_concepts" does not exist` while creating
`candidate_profile_skills`. This issue is the repair, not an improvement.

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

- **`.github/workflows/e2e.yml` runs its own migration.** Line 80 is a bare
  `alembic upgrade head` in `backend/`, followed by seeding the catalogue.
  It must run the platform chain first. This is the step that is failing on
  `main` right now, so it is not optional and not deferrable.
- Search for any other consumer before you finish. Two are known — the compose
  `migrate` service and the e2e workflow. Confirm there is no third: anything
  that migrates a database has to run both chains, in order.

## Out of scope
Airflow services — issue 08.

## Acceptance
- `docker compose up` from a clean volume brings the API to healthy.
- `docker compose down -v && docker compose up` repeats it.
- Both `alembic_version` and `alembic_version_platform` exist and are at head.

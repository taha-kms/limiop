# 01 — Hold the catalog in an external volume

## Why
Every run against real postings has been verified in a database that was then
deleted. The delivery plan has carried "no environment holds them persistently"
as an open item since Phase A, and Phase C builds on the assumption that a
database survives.

There is no VPS yet, so the persistent environment is this machine. An external
Docker volume is the mechanism: Compose removes named volumes on
`docker compose down -v`, and deliberately does not remove external ones.

## Scope
- `docker-compose.yml`: the PostgreSQL volume becomes external. Give it a
  stable name through a variable with a default, e.g.
  `${SKILLSYNC_POSTGRES_VOLUME:-skillsync_postgres_data}`, so a different
  machine can point at a different volume without editing the file.
- The volume must be created before the first `docker compose up`, or Compose
  refuses to start. Document the one-time command in `README.md` next to the
  existing local-development instructions, and add the variable to
  `.env.example`.
- Document the deliberate reset too. `down -v` no longer destroys the catalog,
  which is the point, so a developer who wants a clean database needs to be
  told how: remove the volume by name, explicitly.
- Airflow's metadata database lives in the same PostgreSQL server and therefore
  becomes persistent as well. That is correct — DAG history and run state
  surviving a restart is the behaviour we want — but say so in the README so it
  is not a surprise.
- **Check CI before you finish.** If any workflow runs `docker compose up`, it
  needs the volume created first. `docker compose config --quiet` does not.
  Search for both rather than assuming.

## Portability
This has to survive the move to a VPS without redesign. The same Compose file
and the same external volume work there unchanged, and moving to a managed
PostgreSQL later should be a change to `SKILLSYNC_DATABASE_URL` and nothing
else. Do not introduce anything that ties the setup to this machine — no
absolute host paths, no bind mounts to a home directory.

## Out of scope
Backups, replication, and anything about a hosted environment. Those are
deployment decisions that have not been made.

## Acceptance
Prove the survival property, do not assert it:

1. Create the volume, `docker compose up`, and seed the catalog.
2. Record the row count: `select count(*) from jobs;`
3. `docker compose down -v`
4. `docker compose up` again.
5. The row count is unchanged. Paste both numbers.

Also:
- `docker compose config --quiet` passes.
- A developer following only the README, on a machine with no volume, gets a
  working stack.
- Removing the volume by name and starting again yields an empty, migrated
  database.

Note: these need a Docker daemon. If you have none, do the work and state
precisely which criteria are unverified.

# 03 — Split the Alembic chain

## Why
Migrations for the shared tables have to ship with the package that owns them.
Today one chain in `backend/alembic` covers all eleven tables.

**This is the highest-risk change in the sequence. It touches migration history
on a database that already has ten applied revisions.**

## Scope
Two chains against one database.

- `platform/db/alembic/` with `version_table = "alembic_version_platform"`,
  covering `jobs`, `companies`, `job_sources`, `job_provenance`,
  `skill_concepts`, `skill_surface_forms`, `skill_alias_versions`.
- `backend/alembic/` keeps `version_table = "alembic_version"`, covering
  `users`, `cvs`, `candidate_profiles`, `candidate_profile_skills`.
- Both `env.py` files set `include_object` to filter to their own tables, so
  autogenerate in one chain never proposes dropping the other's tables. Filter
  on an explicit table-name set, not on which module the model came from — an
  explicit list fails loudly when a table is added without a decision about who
  owns it.
- The platform chain starts from a single baseline revision that creates the
  seven shared tables in their **current** shape, as produced by the existing
  revisions `0002` through `0010`. Read those files; do not guess the shape.
- The backend chain is rewritten to cover only its four tables. Its existing
  `0001_database_baseline` and the job/skill revisions are replaced.
- Because both baselines describe tables that already exist in a deployed
  database, document the upgrade path for an existing database in
  `docs/superpowers/specs/2026-08-25-service-extraction/migration-notes.md`:
  which `alembic stamp` commands to run, in which order, and how to confirm.
  A fresh database must come up correctly from both chains with no stamping.

## Out of scope
Any change to table shape. The two chains must produce byte-identical schema to
what `backend/alembic upgrade head` produces today.

## How to prove it

Take the reference dump **before** you change anything. Once the chain is
rewritten there is nothing left to compare against, and reconstructing it from
git mid-task is where this goes wrong.

1. Create database `ref` on the PostgreSQL server you were given. Run the
   current single chain into it: `alembic upgrade head` from `backend/`.
   Dump it: `pg_dump --schema-only --no-owner --no-privileges`. Keep that file
   outside the repository, in /tmp.
2. Now do the work.
3. Create database `split`. Run the platform chain into it, then the backend
   chain. Dump it the same way.
4. Diff the two dumps. The only permitted differences are the
   `alembic_version` and `alembic_version_platform` tables and their contents.
   Any difference in an application table, index, constraint, or default means
   a baseline is wrong. Fix the baseline. Do not add a migration to reconcile
   it, and do not edit the dumps.
5. Paste the actual diff in your final message, even when it is empty.

## Acceptance
- Against an empty PostgreSQL: run the platform chain, then the backend chain,
  and the resulting schema matches today's `upgrade head` output. Prove it by
  dumping both schemas (`pg_dump --schema-only`) and diffing them. Attach the
  diff — it must be empty apart from the `alembic_version*` tables.
- `alembic revision --autogenerate` in each chain produces an empty migration.
- `alembic downgrade base` works in each chain.
- Integration tests pass against a real PostgreSQL.

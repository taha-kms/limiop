---
name: database-development
description: Develop and modify SkillSync's PostgreSQL persistence layer using SQLAlchemy and Alembic. Use whenever work changes database models, relationships, constraints, indexes, migrations, transactions, persistence queries, PostgreSQL-specific behavior, or database contracts shared by the FastAPI backend, Airflow, data engineering, analytics, or ML. Keep schema changes explicit, migration-safe, tested against PostgreSQL where database semantics matter, and compatible with the repository task and Git workflow.
---

# SkillSync Database Development

## Start with repository context

Before changing database behavior:

1. Read `AGENTS.md` and `docs/PROJECT_CONTEXT.md`.
2. Inspect the existing SQLAlchemy models, Alembic configuration, migrations, repositories/services, and database tests.
3. Follow the issue/branch/commit/PR workflow defined by the repository. Do not duplicate Git workflow rules here.
4. Determine every consumer affected by the database contract: backend, Airflow, data engineering, analytics, or ML.

## Keep one schema authority

Treat PostgreSQL as SkillSync's primary application and pipeline persistence layer.

Use SQLAlchemy models and Alembic migrations as the authoritative schema-management path. Do not create a second independent migration system inside Airflow or data-engineering code.

If pipeline work requires a schema change, coordinate that change through the same database migration path.

## Model relational data deliberately

Prefer normalized relational tables for stable domain concepts such as:

- users
- CV metadata
- companies
- jobs
- skills
- job-skill relationships
- CV-skill relationships
- job matches
- saved jobs
- pipeline/model metadata

Use JSON/JSONB only when the data is genuinely semi-structured or source-specific. Do not use JSONB to avoid designing a schema.

Read `references/schema-design.md` when adding or restructuring tables, columns, relationships, constraints, or indexes.

## Make constraints enforce real invariants

Enforce important invariants in PostgreSQL where practical instead of relying only on Python checks.

Use appropriate:

- primary keys
- foreign keys
- unique constraints
- non-null constraints
- check constraints
- indexes

Prefer stable source identifiers for ingested jobs when a provider supplies them. Preserve provenance and original application URLs.

Do not create uniqueness rules from fuzzy business assumptions without evidence.

## Use migrations for schema changes

Every persistent schema change must be represented by an Alembic migration once migrations are established.

Never rely on `create_all()` as a production migration strategy.

Never manually edit production schema state as part of normal development.

Read `references/migration-rules.md` before adding, removing, renaming, or changing persistent columns/tables.

## Design for safe evolution

Prefer backward-compatible changes when a deployment may temporarily run mixed application versions.

For risky changes, use an expand/migrate/contract sequence:

1. add the new compatible structure
2. deploy code that can work with it
3. migrate/backfill data safely
4. switch reads/writes
5. remove obsolete structure in a later migration

Do not combine a destructive schema change with unrelated feature work.

## Keep transaction boundaries explicit

Let service or persistence boundaries control transactions. Avoid hidden commits deep inside reusable helpers unless the established repository pattern explicitly requires them.

Use transactions for operations that must succeed or fail together.

Rollback on failure and propagate useful errors.

Do not hold transactions open while performing slow network calls or model inference.

Read `references/queries-and-transactions.md` for query, locking, concurrency, and transaction rules.

## Make ingestion persistence idempotent

Data-pipeline writes must tolerate retries and reruns.

Prefer database-supported upsert/idempotency patterns backed by constraints rather than check-then-insert races.

Do not depend only on in-memory deduplication for persistent uniqueness.

Preserve lifecycle/provenance fields required by data engineering, such as source identity and first/last observation timestamps where the canonical contract defines them.

## Index from access patterns

Add indexes to support demonstrated query/filter/join patterns, not because a column looks important.

Consider indexes for fields frequently used in:

- foreign-key joins
- active-job filtering
- source identifiers
- publication/observation dates
- user-to-match/saved-job lookup
- common job filters

Avoid speculative indexes. Each index adds write and maintenance cost.

For non-trivial query changes, inspect the generated SQL and use PostgreSQL query plans when performance is part of the task.

## Keep timestamps and identifiers consistent

Use the repository's established identifier strategy.

Store timestamps consistently and timezone-aware where practical. Prefer UTC for persisted system timestamps and convert only at presentation boundaries.

Do not mix naive and timezone-aware timestamps in the same contract.

## Protect user data

Treat CV-derived records and account data as sensitive.

Do not log or expose unnecessary personal data.

Do not store original CV binaries directly in PostgreSQL when object storage is the intended file boundary.

Store only required metadata, parsed/structured data, and storage references according to the project design.

## Test database behavior

Database changes are incomplete without relevant tests.

Use PostgreSQL integration tests when behavior depends on PostgreSQL semantics such as constraints, transactions, JSONB, indexes, locking, or upserts.

Do not use SQLite as proof that PostgreSQL-specific behavior works.

Read `references/database-testing.md` for migration, model, constraint, and persistence testing rules.

## Finish cleanly

Before completing database work:

- verify model and migration agreement
- apply migrations from a clean database where feasible
- test upgrade paths
- test important constraints and persistence behavior
- inspect generated SQL for risky query changes
- confirm no destructive migration is accidental
- update affected API/pipeline contracts and docs
- run the relevant CI checks

---
name: airflow-development
description: Develop and modify the SkillSync Apache Airflow data platform. Use for DAGs, schedules, task dependencies, job-source ingestion, normalization, deduplication, enrichment, data-quality checks, retries, idempotency, backfills, pipeline persistence, Airflow configuration, providers, and Airflow tests. Apply this skill whenever a task changes files under SkillSync's airflow directory or changes a contract owned by the data pipeline. Follow the repository task workflow and Git rules separately.
---

# SkillSync Airflow Development

Build Airflow changes as orchestration around reusable, testable Python code. Keep DAG definitions small and make pipeline behavior reproducible.

## Start Every Task

1. Read the repository-root `AGENTS.md`.
2. Read `docs/PROJECT_CONTEXT.md`.
3. Inspect the existing `airflow/` implementation and nearby tests before editing.
4. Check the Airflow version pinned by the repository before choosing imports or APIs.
5. Follow the issue, branch, commit, and pull-request workflow defined by the repository. Do not duplicate or weaken those rules here.
6. Read only the reference files relevant to the task:
   - Pipeline ownership and layout: `references/pipeline-architecture.md`
   - DAG and task authoring: `references/dag-and-task-rules.md`
   - Source ingestion and persistence: `references/ingestion-and-persistence.md`
   - Idempotency and data quality: `references/data-quality-and-idempotency.md`
   - Testing and operations: `references/testing-and-operations.md`

## SkillSync Airflow Responsibilities

Use Airflow to orchestrate repeatable data workflows for:

- ingesting jobs from approved external sources;
- preserving raw source payloads where practical;
- validating and normalizing source data;
- deduplicating jobs;
- enriching jobs with normalized skills and metadata;
- marking stale or expired jobs appropriately;
- producing analytics-ready data;
- orchestrating model training or evaluation jobs when required.

Do not make Airflow responsible for:

- frontend behavior;
- FastAPI request handling;
- user authentication or authorization;
- interactive job matching requests;
- synchronous ML inference for API requests;
- application UI state;
- arbitrary long-lived business logic embedded inside DAG files.

## Core Architecture Rule

Prefer this dependency direction:

```text
DAG / Task definition
        |
        v
Reusable pipeline module
        |
        +--> source client
        +--> transformation
        +--> validation
        +--> repository / persistence boundary
```

Do not build this:

```text
DAG file
  +--> HTTP calls
  +--> 300 lines of cleaning
  +--> SQL strings
  +--> ML logic
  +--> notification logic
```

DAG files describe orchestration. Normal Python modules perform the work.

## Repository Layout

Prefer the existing structure. If the relevant area does not exist yet, use this direction rather than inventing an unrelated layout:

```text
airflow/
├── dags/
│   ├── job_ingestion.py
│   ├── job_enrichment.py
│   ├── job_expiration.py
│   └── model_training.py
├── src/
│   ├── ingestion/
│   ├── normalization/
│   ├── deduplication/
│   ├── enrichment/
│   ├── quality/
│   └── persistence/
├── tests/
└── Dockerfile
```

Do not create directories speculatively. Add structure when code actually needs it.

## Airflow Version Discipline

Treat the repository's pinned Airflow version as the source of truth.

- Use APIs supported by the pinned version.
- Prefer Airflow's public authoring interfaces rather than internal scheduler or metadata-database internals.
- For Airflow 3+, prefer the stable public authoring interfaces exposed through the Task SDK where appropriate.
- Do not copy examples from another major Airflow version without adapting them.
- Do not upgrade Airflow or providers as part of an unrelated feature.

If the repository has no pinned version yet, establish one explicitly before relying on version-specific APIs.

## DAG Design

Each DAG must have one clear purpose.

Prefer separate DAGs such as:

```text
job_ingestion
job_enrichment
job_expiration
analytics_aggregation
model_training
```

instead of one giant DAG that performs every data operation.

For every DAG, define intentionally:

- stable `dag_id`;
- schedule or explicit manual-only behavior;
- start date;
- catchup behavior;
- task retries and retry delay where appropriate;
- task timeouts where useful;
- concurrency or pool controls for rate-limited sources;
- tags or ownership metadata according to repository conventions.

Do not rely on Airflow defaults when the default could materially change pipeline behavior.

## Thin DAG Files

Keep imports and top-level DAG parsing lightweight.

Do not perform at module import time:

- external API calls;
- database queries;
- file downloads;
- expensive model loading;
- large transformations;
- network-based configuration discovery.

Those operations belong inside tasks or reusable modules called by tasks.

## Task Boundaries

Create tasks around observable units of work.

Good boundaries include:

```text
fetch_arbeitnow_jobs
persist_raw_jobs
normalize_jobs
deduplicate_jobs
extract_job_skills
upsert_jobs
run_quality_checks
```

Avoid both extremes:

- one task that performs the entire pipeline;
- hundreds of tiny tasks for trivial in-memory function calls.

Split tasks when the boundary improves retry behavior, observability, parallelism, or failure isolation.

## TaskFlow and Operators

Use TaskFlow-style tasks when they make Python orchestration clearer and are supported by the pinned Airflow version.

Use provider operators and hooks when they provide a maintained integration that is clearer than custom plumbing.

Do not introduce a custom operator merely to wrap a small Python function. Create custom operators only when the behavior is genuinely reusable as an Airflow abstraction.

## Data Passing

Do not pass large job datasets through XCom.

Use XCom only for small control or metadata values such as:

- object-storage keys;
- batch identifiers;
- counts;
- timestamps;
- status metadata;
- small lists used for mapping when safely bounded.

Persist substantial data to the appropriate database or object-storage layer and pass a reference between tasks.

## External Job Sources

Initial SkillSync sources may include:

- Arbeitnow;
- Jobicy;
- selected Greenhouse public job boards;
- selected Lever public postings;
- ESCO for skill and occupation normalization.

Give each source its own client or adapter. Do not spread source-specific response handling throughout DAG code.

Normalize all source records toward the canonical SkillSync job contract before application-facing persistence.

Preserve source attribution and the original application URL.

## Source Reliability

Treat all external sources as unreliable and untrusted.

Every source integration must consider:

- request timeout;
- retryable versus non-retryable failures;
- rate limits;
- pagination;
- malformed responses;
- missing fields;
- duplicate records;
- invalid dates;
- source outages;
- HTML or unexpected text in descriptions;
- schema changes.

Do not retry deterministic validation errors forever.

## Idempotency

Airflow tasks must be safe to retry whenever practical.

Do not design a task so rerunning the same logical interval silently duplicates jobs or corrupts state.

Prefer:

- deterministic natural/source keys;
- upserts where appropriate;
- batch/run identifiers;
- unique constraints;
- explicit raw-versus-normalized boundaries;
- repeatable transformations.

A retry should repeat work safely, not create a second reality.

## Data Quality

Validate data at meaningful boundaries.

Check at least what is relevant to the source or transformation, such as:

- required identifiers;
- job title presence;
- source attribution;
- valid application URL;
- parseable dates;
- allowed employment or remote values;
- duplicate rates;
- unexpectedly empty batches;
- unacceptable null rates;
- record-count anomalies.

Fail the task when bad data would make downstream results misleading. Quarantine or record recoverable bad rows when that is more appropriate than failing an entire batch.

## Raw Data

Preserve raw source payloads where practical and useful for debugging or replay.

Keep a clear distinction between:

```text
raw source data
      -> validated data
      -> normalized data
      -> enriched/application data
```

Do not mutate raw data in place and then call it raw.

## Persistence

Use explicit persistence boundaries instead of scattering database calls across transformations.

- Keep transformation functions independent of Airflow where practical.
- Keep SQLAlchemy/database session handling out of pure transformation functions.
- Use transactions around coherent writes.
- Prefer bulk operations for large batches when safe.
- Enforce deduplication with database constraints as well as application logic where possible.
- Do not store large binaries or model artifacts in PostgreSQL.

Coordinate schema ownership with the backend/database conventions rather than creating a competing schema from Airflow.

## Scheduling

Choose schedules from product/data freshness requirements, not arbitrary cron enthusiasm.

For job ingestion, use a cadence that respects source limits and provides useful freshness. Do not poll a source more frequently than its terms or limits allow.

Set `catchup` deliberately. Historical backfills should be intentional and must not accidentally hammer external APIs.

Use asset-aware/event-driven scheduling only when it materially improves dependencies and the pinned Airflow version supports the chosen pattern.

## Backfills

Before making a DAG backfillable, verify:

- tasks are idempotent;
- source data can be retrieved historically or replayed from raw storage;
- logical dates are used consistently;
- writes do not duplicate current records;
- external APIs will not be called once per historical interval unless that is actually intended.

Do not assume every scheduled DAG should support arbitrary backfills.

## Concurrency and Rate Limits

Protect external sources and internal services.

Use Airflow pools, task concurrency, mapped-task limits, or equivalent supported controls when parallel execution could exceed:

- API quotas;
- database capacity;
- CPU or memory limits;
- model-service capacity.

Do not create unbounded dynamic task mapping from arbitrary source data.

## Secrets and Connections

Never hardcode credentials in DAGs or Python modules.

Use the repository-approved secret/environment strategy and Airflow Connections or secret backends where appropriate.

Do not log connection strings, tokens, passwords, CV contents, or sensitive user data.

Do not access Airflow's metadata database directly to retrieve internal connection or variable records from task code when a public API or supported mechanism exists.

## Logging and Observability

Log enough context to diagnose pipeline behavior without leaking sensitive data.

Useful context includes:

- source name;
- batch or run identifier;
- number of fetched records;
- number of accepted/rejected records;
- number of inserted/updated/deduplicated records;
- failure category.

Avoid dumping full external payloads into normal logs.

## Model Workflows

Airflow may orchestrate model training or evaluation, but model implementation belongs under the ML component.

Prefer:

```text
Airflow DAG
    -> invoke training/evaluation module
    -> store model artifact externally
    -> persist model metadata
```

Do not train models inside DAG-definition code.

Do not make synchronous API inference depend on an Airflow task being available.

## Testing

Test reusable pipeline logic independently from Airflow whenever possible.

Add tests for meaningful changes, including relevant cases such as:

- source response parsing;
- pagination;
- normalization;
- deduplication;
- idempotent persistence;
- malformed records;
- rate-limit or transient failures;
- data-quality checks;
- DAG import/parse correctness;
- expected task dependencies.

Mock external HTTP boundaries in unit tests. Use integration tests for real persistence behavior where valuable.

Do not call live job APIs from normal CI test suites.

## Failure Handling

Classify failures rather than applying retries indiscriminately.

Retry likely transient failures such as temporary network or service errors.

Fail without pointless repeated retries for deterministic problems such as invalid configuration, unsupported schema, or irrecoverably malformed required data.

Make partial-failure behavior explicit. Do not silently report a successful DAG when a required source or transformation failed.

## Code Quality

Keep pipeline code:

- typed where practical;
- deterministic where practical;
- modular;
- testable without starting an Airflow scheduler;
- free of hidden global state;
- explicit about time zones and dates;
- explicit about source-specific assumptions.

Avoid broad `except Exception` handlers unless they re-raise after adding useful context or are at a deliberate boundary that can classify the error safely.

## Cross-Component Changes

If a pipeline task also changes:

- backend-owned API or persistence contracts, apply the backend-development guidance;
- ML training or inference contracts, apply the ML-development guidance when available;
- CI/CD or deployment behavior, follow the repository's CI/CD rules;
- frontend behavior, do not modify it casually as part of a pipeline issue.

Split unrelated cross-component work into separate issues when practical.

## Completion Checklist

Before completing an Airflow task, verify:

- the DAG has one clear responsibility;
- DAG import/top-level code is lightweight;
- reusable logic lives outside DAG definitions;
- source calls have timeouts and controlled retries;
- writes are idempotent where practical;
- large payloads are not passed through XCom;
- source attribution and application URLs are preserved;
- data-quality checks cover the changed boundary;
- secrets are not hardcoded or logged;
- relevant unit/integration/DAG tests pass;
- the diff contains no unrelated refactor;
- repository Git and PR rules have been followed.

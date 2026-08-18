---
name: data-engineering
description: Develop and modify SkillSync data-engineering code for job-source ingestion, raw-data capture, validation, canonical normalization, deduplication, enrichment, ESCO skill mapping, PostgreSQL persistence, analytics-ready datasets, data-quality checks, and pipeline tests. Use whenever work changes SkillSync's job-data contracts, source adapters, transformations, provenance, quality rules, historical snapshots, or data passed between Airflow, PostgreSQL, analytics, and ML. Keep Apache Airflow focused on orchestration and keep reusable data logic in ordinary Python modules. Follow repository task and Git rules separately.
---

# SkillSync Data Engineering

## Purpose

Build reproducible, source-aware data pipelines that turn unreliable external job data into trustworthy SkillSync application, analytics, and ML inputs.

Do not treat a successful API request as successful data engineering. The output must also be valid, traceable, idempotent, testable, and safe to rerun.

## Start Every Task

1. Read `AGENTS.md` and `docs/PROJECT_CONTEXT.md`.
2. Inspect the existing pipeline code, schemas, database constraints, migrations, fixtures, and tests before changing anything.
3. Identify the stage owned by the change: extraction, raw capture, validation, normalization, deduplication, enrichment, persistence, or analytics preparation.
4. Preserve the existing canonical data contract unless the task explicitly changes it.
5. Follow the repository issue -> branch -> small commits -> pull request workflow from `AGENTS.md`.
6. Use the `airflow-development` rules as well when changing DAGs, schedules, task dependencies, retries, pools, or backfills.

## Ownership Boundary

Data engineering owns:

- external job-source adapters and source contracts
- raw job payload capture and ingestion metadata
- validation and schema-drift handling
- canonical job normalization
- deterministic deduplication and provenance
- job expiration / activity-state data rules
- ESCO and deterministic skill-taxonomy enrichment
- data-quality checks and pipeline metrics
- persistence logic used by ingestion pipelines
- analytics-ready aggregates and historical snapshots
- data-pipeline fixtures and transformation tests

Data engineering does **not** own:

- FastAPI request/response behavior
- frontend presentation logic
- Airflow scheduling semantics beyond the processing contract
- ML model architecture or training algorithms
- authentication or authorization

Keep those concerns in their owning project areas.

## Preferred Code Placement

For pipeline-owned logic, prefer modules under `airflow/src/` such as:

```text
airflow/src/
├── ingestion/
├── contracts/
├── normalization/
├── deduplication/
├── enrichment/
├── quality/
├── persistence/
└── analytics/
```

Do not move reusable transformation logic into DAG files. DAGs should call these modules.

Do not import FastAPI routes or web-layer services into data pipelines. If both backend and pipelines need the same pure contract or utility, extract a deliberately shared module rather than creating an accidental dependency on the web application.

## Pipeline Stages

Use this conceptual flow:

```text
External source
    ↓
Raw source record
    ↓
Validated record
    ↓
Canonical normalized record
    ↓
Deduplicated record
    ↓
Enriched record
    ↓
Persistent serving / analytics data
```

Read `references/pipeline-layers-and-contracts.md` before adding a source, changing a canonical record, or changing stage boundaries.

## Source Ingestion

Initial job sources include:

- Arbeitnow
- Jobicy
- Greenhouse public job boards
- Lever public postings
- ESCO for occupation and skill taxonomy data

Read `references/source-ingestion.md` when adding or modifying a source adapter.

Keep each source adapter isolated. Downstream code must not depend on source-specific response shapes.

Always preserve enough provenance to answer:

- where did this record come from?
- what external identifier identified it?
- when did SkillSync fetch it?
- what original application/source URL was supplied?
- which ingestion run processed it?

## Canonical Data

Normalize external records into a stable SkillSync representation before application or analytics use.

At minimum, a job record usually needs a stable source identity, a title, company information where available, job text, publication/activity metadata, location/remote semantics, and a usable original destination URL.

Keep unknown values unknown. Do not convert missing data into convenient but false defaults.

Examples:

- missing remote status is not automatically `false`
- missing salary is not `0`
- missing publication date is not ingestion time
- missing country is not inferred from a weak location string unless the inference is explicit and traceable

## Normalization

Prefer deterministic, testable normalization functions.

Normalize only for a concrete comparison, filtering, analytics, or product need. Preserve useful original values separately when normalization is destructive.

Read `references/normalization-and-deduplication.md` for detailed rules.

## Deduplication

Use strongest identifiers first:

1. source + source job identifier
2. stable/canonical application URL where trustworthy
3. deterministic fingerprints built from normalized identifying fields
4. fuzzy similarity only as a cautious secondary signal

Never merge two jobs solely because titles are similar.

Cross-source deduplication must preserve every source record's provenance even when multiple source records map to one canonical job.

All deduplication and persistence behavior must be safe under retries and reruns.

## Data Quality

Read `references/data-quality.md` whenever adding validation, rejection, quarantine, quality metrics, or schema-drift handling.

Classify fields and checks by consequence rather than making every imperfect record fatal.

Typical outcomes are:

- accept
- accept with null / warning
- repair using an explicit deterministic rule
- quarantine
- reject
- fail the pipeline when systemic corruption is likely

Track quality metrics per source and run. Do not hide large rejection spikes behind successful task status.

## Persistence

Prefer idempotent database writes.

Use:

- database uniqueness constraints where identity is important
- deliberate transactions
- upserts where reruns should update existing records
- stable external/source keys
- `first_seen_at` and `last_seen_at` where useful
- explicit activity/expiration rules

Do not hard-delete historical jobs simply because a source no longer returns them unless the product requirement explicitly demands deletion.

Database schema changes must use the repository's migration process and follow database/backend ownership rules.

Read `references/persistence-and-analytics.md` for persistence and analytical dataset guidance.

## Enrichment and ESCO

Treat enrichment as a separate stage from normalization.

For deterministic taxonomy mapping:

- preserve canonical ESCO identifiers where available
- preserve the original extracted term when useful for debugging
- record mapping/extraction method when multiple methods exist
- keep confidence scores when a result is probabilistic

Do not silently convert uncertain skill extraction into a fact.

ML-driven extraction or ranking belongs to the ML implementation. The pipeline may orchestrate it and persist its outputs using an explicit contract.

## Historical and Analytics Data

SkillSync should be able to answer questions over time, not only show the latest snapshot.

When implementing analytical datasets, make these definitions explicit:

- event/reference timestamp
- aggregation grain
- time zone
- active-job definition
- source population
- deduplication state
- null/unknown handling

Do not hardcode dashboard metrics. Produce them from reproducible data transformations.

## Python Data Processing

Use the repository's existing dataframe library for a given path. Prefer not to mix Pandas and Polars in the same transformation flow without a real reason.

For transformation code:

- favor pure functions where practical
- use explicit schemas/types at boundaries
- avoid hidden global state
- handle time zones explicitly
- avoid row-by-row loops when a clear vectorized/batch approach exists
- avoid loading unbounded datasets into memory
- keep source I/O separate from transformation logic

Do not introduce Spark, Kafka, dbt, a warehouse, or another data platform simply because those words look impressive on architecture diagrams. Add infrastructure only when the data volume or product requirement justifies it.

## Testing

Read `references/testing-data-pipelines.md` before completing meaningful pipeline changes.

At minimum, cover relevant cases such as:

- representative valid source payloads
- missing optional fields
- malformed required fields
- schema drift
- pagination edge cases
- normalization edge cases
- duplicate input
- repeated/rerun input
- database upsert behavior
- timestamps and time zones
- quarantine/rejection behavior
- analytical aggregate correctness

Do not call live third-party job APIs in normal CI tests. Use small sanitized fixtures.

Where PostgreSQL constraints, transactions, JSON types, or upserts matter, test against PostgreSQL rather than pretending SQLite is the same database wearing a smaller hat.

## Logging and Observability

Emit structured enough pipeline metadata to diagnose failures without dumping entire payloads into logs.

Useful run metrics include:

- fetched
- parsed
- accepted
- repaired
- quarantined
- rejected
- deduplicated
- inserted
- updated
- marked inactive
- enrichment success/failure counts

Never log credentials, tokens, CV contents, or unnecessary personal data.

## Completion Check

Before completing data-engineering work, verify that:

- source-specific behavior is isolated
- provenance is retained
- the canonical contract remains explicit
- unknown values are not fabricated
- transformations are deterministic where practical
- retries/reruns do not create duplicate logical records
- malformed data is handled intentionally
- data-quality behavior is observable
- historical behavior is preserved where required
- analytics outputs are reproducible
- tests cover both normal and bad inputs
- DAG files remain orchestration-focused
- no unnecessary infrastructure or dependency was introduced
- repository Git/GitHub rules were followed

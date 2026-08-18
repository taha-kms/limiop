# Data Quality and Idempotency

## Contents

- Idempotent design
- Run and batch identity
- Quality checks
- Quarantine
- Deduplication
- Dates and time zones
- Replay and backfill

## Idempotent Design

Assume tasks may execute more than once.

Use stable identifiers and deterministic writes so retrying the same logical work does not create duplicates.

Preferred techniques include:

- `(source, source_job_id)` uniqueness when stable;
- deterministic fingerprints for sources lacking a stable ID;
- `INSERT ... ON CONFLICT`/SQLAlchemy upsert patterns where appropriate;
- batch identifiers;
- transactional writes;
- staging before promotion for multi-step loads.

Avoid using random identifiers as the only identity for externally sourced records.

## Run and Batch Identity

Distinguish Airflow's task/DAG run identity from the data batch identity when useful.

A batch identifier can connect:

- raw records;
- validation results;
- normalized rows;
- load metrics;
- quality reports.

This makes reruns and debugging substantially less archaeological.

## Quality Checks

Choose checks that can catch materially bad data.

Possible checks:

- batch is not unexpectedly empty;
- required source identifiers are present;
- titles are not blank;
- application URLs are valid enough for the product contract;
- publication dates parse and are plausible;
- duplicate percentage is below an expected threshold;
- normalized enum values are within allowed sets;
- null rates for important fields are within thresholds;
- transformed record count reconciles with accepted/rejected counts.

Use explicit thresholds when a threshold matters. Do not write a check whose only possible outcome is success.

## Quarantine

Not every bad row needs to fail an entire batch.

Use quarantine/rejected-record handling when:

- individual rows are malformed but the source batch is otherwise usable;
- preserving the failed row helps debugging;
- the issue does not invalidate aggregate downstream data.

Fail the whole task when the batch itself is untrustworthy or a required invariant is violated broadly.

Record rejection reason without logging unnecessary personal or source payload data.

## Deduplication

Use a layered strategy:

1. exact identity using source IDs/canonical URLs where reliable;
2. normalized composite keys where needed;
3. optional similarity-based candidate detection for difficult duplicates;
4. database uniqueness constraints for final protection where appropriate.

Do not use fuzzy matching as the only mechanism for every job. It is expensive and can merge distinct roles incorrectly.

## Dates and Time Zones

Use timezone-aware timestamps.

Prefer UTC for storage and pipeline calculations unless the project explicitly requires another basis.

Distinguish:

- source publication time;
- fetch time;
- first-seen time;
- last-seen time;
- logical Airflow data interval.

Do not substitute task execution wall-clock time for a logical data interval when backfill/replay semantics depend on it.

## Replay and Backfill

A replay should ideally produce the same normalized output from the same raw input and code version, subject to explicitly versioned enrichment dependencies.

Before supporting historical backfills against a live source API, determine whether the API can actually return historical data. Otherwise backfill from preserved raw data or make the DAG non-backfillable for that stage.

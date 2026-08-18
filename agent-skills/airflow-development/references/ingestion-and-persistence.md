# Ingestion and Persistence

## Contents

- Source adapters
- HTTP behavior
- Pagination
- Raw preservation
- Canonical normalization
- PostgreSQL persistence
- Job lifecycle
- ESCO

## Source Adapters

Give each source one clear adapter/client boundary.

Examples:

```text
airflow/src/ingestion/arbeitnow.py
airflow/src/ingestion/jobicy.py
airflow/src/ingestion/greenhouse.py
airflow/src/ingestion/lever.py
```

A source client should own:

- URL construction;
- authentication if needed;
- request timeout;
- pagination;
- source-specific error interpretation;
- source response parsing into a source model.

Do not normalize directly to database ORM entities inside HTTP response parsing if a source model makes the boundary clearer.

## HTTP Behavior

Use an existing shared HTTP client if the codebase has one suitable for pipelines.

Always configure a timeout.

Treat status codes intentionally:

- successful response: parse and validate;
- rate limit: respect retry/backoff guidance;
- temporary 5xx/network error: retry according to policy;
- permanent 4xx/config error: fail with actionable context;
- invalid JSON/schema: record source context and fail/quarantine as designed.

Never log tokens or full sensitive request headers.

## Pagination

Pagination must be deterministic and bounded by the source contract.

Track useful metadata such as:

```text
source
page/cursor
records_received
batch_id
fetched_at
```

Avoid silently truncating results because only the first page was implemented.

Protect against infinite pagination when a source repeats cursors/pages unexpectedly.

## Raw Preservation

Where practical, preserve the fetched source payload or a faithful row-level representation before destructive transformation.

Raw storage enables:

- replay;
- debugging source schema changes;
- transformation regression investigation;
- historical audit of what the source returned.

Raw retention can be bounded by cost/privacy policy. Do not pretend a transformed payload is still raw.

## Canonical Normalization

Normalize source records into SkillSync's canonical job representation.

Expected concepts include:

```text
source
source_job_id
title
company
location
country
remote
employment_type
description
published_at
apply_url
source_url
first_seen_at
last_seen_at
is_active
```

Use the actual repository schema as the source of truth when it exists.

Normalize dates, booleans, enums, whitespace, locations, and URLs consistently.

Preserve source-specific fields separately if needed rather than polluting the canonical table with one-off columns for every provider.

## PostgreSQL Persistence

Coordinate database schema with the backend/database owner.

Prefer:

- explicit transactions;
- source/source_job_id uniqueness where supported by source guarantees;
- upserts for repeat ingestion;
- bulk operations for batches;
- database constraints for invariants;
- indexes justified by actual query/write patterns.

Do not rely only on in-memory duplicate checks to protect persistent uniqueness.

Keep transformation code independent from SQLAlchemy sessions where practical.

## Job Lifecycle

A job should have a traceable lifecycle rather than disappearing because a source omitted it once.

Useful fields/metadata include:

```text
first_seen_at
last_seen_at
is_active
source
source_job_id
```

Expiration policy should account for source behavior. Do not mark every missing job inactive immediately unless the source contract makes that reliable.

## ESCO

Treat ESCO as reference/taxonomy data, separate from vacancy ingestion.

Use it to support normalized occupations and skills. Version or timestamp imported taxonomy data so results can be reproduced.

Do not perform expensive ESCO refreshes as part of every job-source ingestion run.

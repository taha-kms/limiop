# Pipeline Layers and Contracts

## Contents

1. Layer model
2. Raw contract
3. Validated contract
4. Canonical job contract
5. Enriched contract
6. Contract-change rules
7. Ownership rules

## 1. Layer Model

Treat the layers as semantic contracts even if some are represented by Python objects rather than separate physical tables.

```text
source -> raw -> validated -> normalized -> deduplicated -> enriched -> serving
```

A stage should make a clear promise about what is true of its output.

## 2. Raw Contract

Raw records should preserve source truth with minimal mutation.

Useful metadata includes:

- `source`
- `source_job_id` when supplied
- `fetched_at`
- ingestion/run identifier
- page/cursor metadata where useful
- source/application URL
- raw payload or a retained representation when source terms/storage policy allow it
- optional payload hash for reproducibility/debugging

Do not sanitize raw data by overwriting the only copy of what the source returned.

## 3. Validated Contract

Validation answers whether a raw record is structurally safe enough to continue.

A validated record should have:

- expected types or safely parsed equivalents
- required identity/presentation fields
- explicit nulls for unavailable optional fields
- parse/quality warnings where relevant

Validation should not perform broad business normalization.

## 4. Canonical Job Contract

Inspect the repository schema before adding fields. A canonical job will commonly include concepts such as:

```text
internal id
source
source_job_id
title
company_name
description_text
description_html (only if deliberately retained/sanitized)
location_text
city
country_code
remote_type
employment_type
salary_min
salary_max
salary_currency
salary_period
published_at
source_updated_at
apply_url
source_url
first_seen_at
last_seen_at
is_active
```

Not every source supplies every optional field.

Use explicit enums/vocabularies for fields such as employment or remote type only when the mapping rules are defined. Preserve `unknown`/null instead of inventing a category.

Store timestamps with timezone semantics. Normalize to UTC for storage unless the existing project convention says otherwise.

## 5. Enriched Contract

Enriched data may add derived information such as:

- normalized skill IDs
- ESCO skill/occupation identifiers
- skill extraction method
- confidence
- normalized location components
- deterministic job fingerprint
- ML-derived embeddings or ranking features where their owning contract permits it

Derived fields should not overwrite source truth.

## 6. Contract-Change Rules

Before changing a contract:

1. identify all producers and consumers
2. inspect frontend/backend/ML dependencies
3. determine whether the change is backward compatible
4. update schema/migrations if persistence changes
5. update fixtures and tests
6. update documentation when external/internal contracts materially change

Do not rename or reinterpret a field silently.

For breaking changes, prefer an explicit migration path over simultaneously changing every layer and hoping CI has philosophical objections.

## 7. Ownership Rules

- Airflow owns orchestration, not record semantics.
- Data-engineering modules own extraction/transformation rules.
- Database migrations/schema ownership follow repository backend/database conventions.
- FastAPI owns application API contracts.
- ML owns learned model behavior.
- Frontend consumes backend contracts rather than pipeline-internal structures.

# Testing Data Pipelines

## Contents

1. Test layers
2. Fixtures
3. Source contract tests
4. Transformation tests
5. Idempotency tests
6. Database tests
7. Analytics tests
8. CI rules

## 1. Test Layers

Use the smallest useful test layer:

- unit tests for pure transforms
- contract/parser tests for provider payloads
- integration tests for PostgreSQL persistence
- DAG tests only for orchestration concerns
- end-to-end pipeline tests for a small representative path when valuable

Do not test pure normalization by booting an Airflow scheduler.

## 2. Fixtures

Keep fixtures small and intentional.

Include representative cases such as:

- valid full record
- minimal valid record
- missing optional fields
- malformed required field
- HTML description
- duplicate record
- Unicode/non-English text
- timezone edge case
- schema-drift example

Strip secrets, personal data, tracking values, and irrelevant bulk content.

## 3. Source Contract Tests

Test:

- response-envelope parsing
- pagination
- empty responses
- malformed response
- source ID extraction
- URL extraction
- source-specific optional fields

Mock HTTP at the adapter boundary. Normal CI should not depend on a third-party site's availability.

## 4. Transformation Tests

For deterministic transformations, assert exact output for representative input.

Cover:

- whitespace/text normalization
- enums
- timestamps
- null handling
- location handling
- HTML-to-text behavior
- skill taxonomy mapping where deterministic

Do not write tests that simply execute a function without asserting its contract.

## 5. Idempotency Tests

Run the same input twice and assert that logical state does not duplicate.

For example:

```text
first run: insert job + source record
second run: update/unchanged same logical records
```

Also test corrected source data updating the intended fields without changing immutable provenance.

## 6. Database Tests

Use PostgreSQL for tests involving:

- unique constraints
- `ON CONFLICT`/upsert behavior
- transactions
- JSON/JSONB
- PostgreSQL-specific indexes/types
- concurrency-sensitive persistence

SQLite is acceptable only for logic that is genuinely database-agnostic.

## 7. Analytics Tests

Use tiny hand-checkable datasets.

Assert:

- grain
- counts
- dedupe behavior
- active-state logic
- time-window boundaries
- null/unknown handling

A dashboard number that looks plausible is not a test oracle.

## 8. CI Rules

Before a PR:

- run relevant unit tests
- run affected integration tests
- run lint/type checks configured by the repo
- ensure fixtures are deterministic
- avoid live network dependency
- ensure tests work with Codecov reporting
- fix new CodeQL/SonarQube findings caused by the change

Do not claim a test was run if it was not.

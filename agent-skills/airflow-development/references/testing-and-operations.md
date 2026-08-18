# Testing and Operations

## Contents

- Test layers
- Source-client tests
- Transformation tests
- Persistence tests
- DAG tests
- CI behavior
- Operational logging
- Failure policy
- Local development

## Test Layers

Prefer a pyramid that keeps most logic testable without Airflow runtime machinery.

```text
Pure transformation unit tests
Source-client unit tests
Persistence integration tests
DAG import/topology tests
Small end-to-end pipeline tests where valuable
```

Do not make every test start the complete Docker Compose environment.

## Source-Client Tests

Mock HTTP boundaries in normal CI tests.

Cover relevant cases:

- successful response;
- pagination;
- empty result;
- timeout;
- retryable failure;
- permanent failure;
- malformed response;
- source schema variation.

Use small realistic fixtures rather than enormous copied API payloads.

Do not call live production job APIs in routine CI.

## Transformation Tests

Pure normalization/deduplication functions should have deterministic tests covering:

- normal records;
- missing optional fields;
- invalid required fields;
- dates;
- whitespace/HTML handling;
- enum normalization;
- duplicate identity rules.

Table-driven/parameterized tests are useful for source field variations.

## Persistence Tests

Use PostgreSQL integration tests for behavior that depends on PostgreSQL semantics, such as:

- uniqueness constraints;
- upserts;
- transactions;
- conflict handling;
- timestamp types;
- indexes/queries where behavior matters.

Do not substitute SQLite if the test is specifically proving PostgreSQL behavior.

## DAG Tests

At minimum, ensure changed DAG files can be imported/parsed and contain the expected task dependencies.

Useful assertions can cover:

- stable DAG ID;
- expected schedule/catchup behavior;
- expected task IDs;
- critical dependency ordering;
- retry configuration where important;
- pool/concurrency configuration for rate-limited sources.

Do not unit-test Airflow itself.

## CI Behavior

Airflow CI should remain compatible with repository quality tooling, including Codecov, CodeQL, SonarQube, and Dependabot where configured.

Keep deterministic tests separate from optional/manual live-source smoke tests.

Pin Airflow and provider dependencies according to the repository dependency strategy. Provider changes can alter behavior independently of Airflow core, so do not casually float unconstrained versions.

## Operational Logging

Emit structured or consistently formatted metrics/context where practical:

```text
source
batch_id
fetched_count
accepted_count
rejected_count
inserted_count
updated_count
duplicate_count
duration/failure category
```

Do not log full CVs, credentials, API tokens, or complete raw payloads by default.

## Failure Policy

A pipeline should not show green when required work failed.

Differentiate:

- source unavailable temporarily;
- source permanently misconfigured;
- partial bad rows;
- total schema incompatibility;
- persistence failure;
- quality-gate failure.

Retries belong on transient failures. Alerts/clear task failures belong on persistent or deterministic failures.

## Local Development

Use the repository's Docker Compose/Airflow local setup when integration behavior must be verified.

For pure modules, run tests directly in the component's Python environment when supported.

Do not require a running scheduler to test a pure normalizer or deduplicator.

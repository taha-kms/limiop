# DAG and Task Rules

## Contents

- Version-safe authoring
- DAG parsing
- Scheduling
- Task design
- TaskFlow and operators
- Dynamic mapping
- XCom
- Retries and timeouts
- Pools and concurrency
- Assets

## Version-Safe Authoring

Check the Airflow version in the repository before changing imports or APIs.

For Airflow 3+, prefer the public authoring interfaces supported by that version, including the Task SDK where the repository has adopted it. Avoid importing internal scheduler/database implementation details.

Do not upgrade a major Airflow version during an unrelated DAG feature.

## DAG Parsing

Airflow repeatedly parses DAG definitions. Keep top-level work cheap.

At DAG module import time, do not:

- call APIs;
- query PostgreSQL;
- download files;
- inspect S3/object storage;
- load ML models;
- perform large dataframe operations.

Build the DAG topology and defer work to runtime tasks.

## Scheduling

Every DAG should make its scheduling intent obvious.

Define deliberately:

- schedule or no schedule;
- start date;
- catchup behavior;
- timezone assumptions;
- max active runs or equivalent controls if overlapping runs are unsafe.

Use UTC internally unless project requirements explicitly require another timezone.

Do not calculate a dynamic `start_date` such as `datetime.now()` on every parse.

## Task Design

A task boundary should improve one or more of:

- retry isolation;
- observability;
- parallelism;
- operational ownership;
- data-quality visibility.

Do not create an Airflow task for every trivial helper function.

Avoid a single task that fetches every source, transforms every row, writes everything, and runs quality checks with no intermediate observability.

## TaskFlow and Operators

Use TaskFlow for normal Python tasks when the pinned version supports it and it keeps dependencies readable.

Use maintained provider hooks/operators for external systems when they are a good fit.

Use plain reusable Python modules underneath both styles so business/data logic is not trapped inside Airflow decorators.

## Dynamic Mapping

Use dynamic task mapping only for runtime fan-out that has a bounded and meaningful unit of work.

Good candidates:

- a known bounded list of configured job sources;
- a bounded set of company boards;
- partitioned work where each item is independently retryable.

Do not map one task per arbitrary job posting or unbounded API result.

Apply mapping limits/concurrency controls where a source list can grow.

## XCom

XCom is for orchestration metadata, not bulk transport.

Good:

```text
batch_id
raw_object_key
record_count
source_name
small bounded source list
```

Bad:

```text
20,000 job descriptions
large dataframe
model binary
PDF contents
raw API archive
```

Store bulk data in PostgreSQL or object storage and pass references.

## Retries and Timeouts

Configure retries based on failure type and external-system behavior.

Examples:

- temporary network failure: retry;
- HTTP 429: retry with source-aware backoff when permitted;
- invalid API credential/configuration: fail quickly;
- malformed required schema: fail or quarantine according to pipeline policy;
- deterministic validation failure: do not loop through identical retries.

Set request timeouts in HTTP clients even when Airflow task retries exist. A retry policy cannot rescue a request that hangs forever.

Use task execution timeouts for operations that otherwise can run indefinitely.

## Pools and Concurrency

Use pools or supported concurrency controls for scarce resources and rate-limited APIs.

Examples:

```text
job_api_pool
postgres_write_pool
ml_training_pool
```

Choose names according to existing repository conventions.

Do not increase parallelism solely because Airflow can create more task instances.

## Assets

Use Airflow assets (called datasets in older versions) when data-driven dependencies are clearer than time-only schedules and the pinned version supports them.

Do not introduce asset-aware scheduling merely to appear sophisticated. Use it when one pipeline truly depends on successful production/update of another data asset.

# Persistence and Analytics

## Contents

1. PostgreSQL persistence
2. Provenance
3. Job lifecycle
4. Transactions and batches
5. Analytics-ready data
6. Historical snapshots
7. ML handoff

## 1. PostgreSQL Persistence

SkillSync uses PostgreSQL as the primary application datastore.

For pipeline writes:

- rely on stable keys and database constraints
- use transactions deliberately
- use batched inserts/upserts where appropriate
- avoid one transaction per row for large batches
- keep SQL/database details behind a persistence/repository boundary
- test PostgreSQL-specific behavior against PostgreSQL

Do not bypass the repository's migration process when tables/columns/indexes/constraints change.

## 2. Provenance

Never lose source identity merely because records are normalized.

The persistent model should be able to reconstruct or trace:

- original provider
- provider job ID
- source/application URL
- first/last seen timestamps
- ingestion run or source-record reference where the design supports it

Cross-source canonicalization must retain the contributing sources.

## 3. Job Lifecycle

Prefer lifecycle state over destructive deletion for ordinary source disappearance.

Typical concepts:

- first seen
- last seen
- active/inactive
- explicit source expiration when provided

Do not mark a job inactive solely because one ingestion run failed to fetch its source.

Expiration rules should distinguish:

- source explicitly removed/expired job
- source successfully fetched but job disappeared
- source outage / partial pagination failure

## 4. Transactions and Batches

Design writes so partial failures cannot leave misleading half-updated state.

For each operation decide:

- transaction scope
- retry behavior
- conflict key
- update columns
- unchanged-row behavior
- batch size

Avoid large unbounded transactions that make retries expensive.

## 5. Analytics-Ready Data

Analytics transformations should define:

- grain (job, job-day, skill-day, company-day, etc.)
- dimensions
- measures
- source population
- active-state semantics
- dedupe semantics
- time zone/window

Examples of SkillSync analytics:

- active jobs by day
- jobs by role/location
- remote vs hybrid vs onsite
- skill demand over time
- companies with active vacancies
- skill co-occurrence

Do not count raw source records as jobs after cross-source deduplication unless the metric explicitly measures source listings.

## 6. Historical Snapshots

If historical trends are a product requirement, preserve enough state to reconstruct them.

A current `jobs` table alone may not answer how many jobs were active two months ago. Use snapshots, events, or first/last-seen semantics deliberately.

Do not retrofit fake history from current records.

## 7. ML Handoff

Inputs to ML should come from explicit, reproducible data contracts.

Record or pin enough information to reproduce training/evaluation datasets where practical:

- extraction query/filter
- time window
- canonical data version/schema
- feature transformation version or code commit
- label source if labels exist

Do not make ML training depend on undocumented ad-hoc notebook filtering.

# Queries and Transactions

## Queries

- Avoid N+1 query patterns.
- Load only relationships/data needed for the use case.
- Paginate potentially large result sets.
- Keep filtering/sorting in SQL when the database can do it efficiently.
- Avoid loading full job descriptions or CV data when the endpoint only needs summary fields.

## Transactions

- Keep transactions short.
- Do not keep a transaction open across external HTTP requests or expensive model inference.
- Group atomic state changes in one transaction.
- Roll back on errors.
- Do not hide commits inside helpers that callers reasonably expect to compose transactionally.

## Concurrency

Use database constraints and atomic statements to resolve races where possible.

For ingestion, prefer conflict-aware inserts/upserts to a read-then-write uniqueness check.

Use explicit locking only when the correctness requirement cannot be achieved with simpler atomic database operations.

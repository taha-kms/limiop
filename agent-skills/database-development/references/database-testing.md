# Database Testing

Test database behavior at the right level.

## Model/constraint tests

Verify:

- required relationships
- uniqueness rules
- nullability/invariants
- cascading behavior when intentionally configured

## Persistence tests

Verify:

- inserts and updates
- idempotent ingestion writes
- transaction rollback behavior
- pagination/filter behavior for important queries
- concurrency-sensitive logic when relevant

## Migration tests

At minimum, ensure a clean PostgreSQL database can migrate to head.

For significant migrations, test upgrading from the previous expected revision with representative data.

## PostgreSQL fidelity

Use PostgreSQL for tests of PostgreSQL-specific behavior. SQLite is acceptable only for code that is truly database-agnostic and when the existing repository intentionally uses it for that test layer.

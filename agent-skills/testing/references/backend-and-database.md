# Backend and Database Tests

## API

Test status codes, response schemas, validation, permissions, and meaningful errors.

Do not assert irrelevant serialization ordering unless the API contract requires it.

## Services

Test business rules independently from HTTP where possible.

Mock external clients at the boundary, not internal helper chains.

## Database

Use isolated database state per test/session according to repository fixtures.

For PostgreSQL-specific behavior, test PostgreSQL rather than substituting SQLite.

Verify transactions, rollback, constraints, and idempotent persistence where they matter.

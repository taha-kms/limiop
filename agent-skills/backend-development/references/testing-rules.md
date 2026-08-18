# Backend Testing Rules

## Test Layers

Use the smallest useful test type.

### Unit tests

Use for pure or mostly isolated service/domain logic. Keep them fast and avoid unnecessary database/network setup.

### API tests

Use for FastAPI routing, validation, authentication, authorization, status codes, and response contracts.

### Database integration tests

Use when correctness depends on ORM mappings, constraints, relationships, transactions, or PostgreSQL-specific behavior.

### External client tests

Mock HTTP/network boundaries with realistic responses. Test malformed payloads, timeouts, rate limiting/error responses, and missing fields where relevant.

## Test Structure

Prefer descriptive behavior names such as:

```text
test_create_cv_rejects_unsupported_file_type
test_get_job_returns_404_for_missing_job
test_user_cannot_read_another_users_cv
test_create_job_rejects_duplicate_source_id
```

Avoid tests that merely reproduce implementation steps.

## Fixtures

Keep fixtures focused. Prefer small builders/factories over giant shared fixtures containing unrelated state.

Do not make tests depend on execution order.

Do not call live public job APIs from the normal test suite.

## Assertions

Assert externally meaningful behavior. For API tests, check the status code and relevant response contract. For persistence tests, verify durable state and constraints. For authorization tests, verify both allowed and denied paths.

## Coverage

Codecov is a signal, not the goal. Cover meaningful branches and failures instead of manufacturing assertions that exist only to increase a percentage.

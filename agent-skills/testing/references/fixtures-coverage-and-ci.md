# Fixtures, Coverage, and CI

## Fixtures

Prefer small explicit factories and fixtures. Keep synthetic identities obviously fictional.

Never copy production secrets or personal user content into test data.

## Coverage

Generate coverage in a format accepted by the repository's Codecov workflow.

Use patch/changed-code coverage as a review signal where configured, but do not sacrifice meaningful tests for a percentage target.

## CI

Tests must not depend on developer-local state.

Pin or provision required services explicitly. Fail with useful diagnostics when a required test dependency is missing.

Keep fast PR tests separate from deliberately expensive/nightly checks when the repository introduces those categories.

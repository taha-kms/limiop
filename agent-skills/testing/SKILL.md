---
name: testing
description: Design, write, review, and maintain automated tests across the SkillSync monorepo. Use whenever work adds or changes pytest, Playwright, backend/API tests, PostgreSQL integration tests, Airflow DAG/task tests, data-pipeline quality tests, frontend component or end-to-end tests, ML correctness/evaluation tests, fixtures, test infrastructure, coverage behavior, or flaky-test handling. Keep tests behavior-focused, deterministic, isolated from live external services in normal CI, and compatible with Codecov and the repository task workflow.
---

# SkillSync Testing

## Start with context

Before changing tests:

1. Read `AGENTS.md` and `docs/PROJECT_CONTEXT.md`.
2. Inspect the implementation and existing tests in the affected area.
3. Follow existing test commands, fixtures, naming conventions, and directory structure where they are sound.
4. Determine the lowest-cost test level that can reliably prove the behavior.

Do not duplicate issue/branch/commit/PR rules from `AGENTS.md`.

## Test behavior, not implementation trivia

Write tests around contracts and observable behavior.

Prefer assertions such as:

- an unauthorized user cannot read another user's CV
- duplicate ingestion does not create a second canonical job
- an invalid provider payload is quarantined/rejected as designed
- a match endpoint returns a valid ranked response

Avoid tests whose only purpose is to mirror private method calls or internal variable structure.

## Use a layered test strategy

Use:

- unit tests for pure/small logic
- integration tests for subsystem boundaries such as PostgreSQL or FastAPI+persistence
- end-to-end tests for critical user journeys
- evaluation tests for ML quality

Do not turn every behavior into an end-to-end test. Do not mock everything until the test proves only that the mock works.

Read `references/test-levels.md` for selection rules.

## Backend and database testing

Use `pytest` for Python tests.

Test:

- service behavior
- request/response validation
- authentication/authorization
- error mapping
- persistence behavior
- migrations/constraints where relevant

Use PostgreSQL integration tests for PostgreSQL-specific behavior.

Read `references/backend-and-database.md` for details.

## Airflow and data-pipeline testing

Test DAG structure/importability separately from transformation logic.

Keep reusable transformations testable as ordinary Python functions/modules.

Do not call live Arbeitnow, Jobicy, Greenhouse, Lever, ESCO, or other third-party services in normal CI tests. Use recorded/synthetic fixtures or mocked HTTP boundaries.

Test idempotency, malformed data, schema drift, duplicates, missing fields, and retry-safe behavior.

Read `references/airflow-and-data.md` for details.

## Frontend testing

Use Playwright for important browser-level flows.

Prefer lower-level TypeScript/component tests only if the repository adopts a supported frontend unit-test runner; do not introduce one merely to test trivial rendering.

Test critical flows such as:

- authentication boundaries
- CV upload validation
- job browsing/filtering
- recommended-job display
- external apply-link behavior
- meaningful loading/error/empty states

Use resilient selectors based on roles, labels, and accessible names where practical.

Read `references/frontend-and-e2e.md` for details.

## ML testing and evaluation

Separate software correctness from model quality.

Unit tests should validate:

- preprocessing contracts
- feature shapes/types
- deterministic scoring logic
- artifact loading
- inference schemas
- edge cases

Evaluation should validate whether a model is actually useful using the metrics defined by the ML development skill.

Do not make a CI unit test depend on a huge remote model download unless the repository deliberately provisions that test environment.

Read `references/ml-testing.md` for details.

## Keep fixtures safe and realistic

Use synthetic or deliberately licensed/public fixture data.

Never commit real user CVs, credentials, production dumps, or private job-source data.

Keep fixtures small and focused. Build reusable factories for repetitive domain setup.

Avoid fixture systems so abstract that a reader cannot tell what data a test actually uses.

## Keep tests deterministic

Control:

- random seeds where randomness matters
- current time through clocks/freezing when time affects behavior
- external HTTP calls
- environment variables
- temporary files
- database state

Avoid arbitrary sleeps.

If asynchronous behavior must be awaited, wait on the actual condition or event.

## Treat flaky tests as defects

Do not hide flaky tests behind unlimited retries.

When a test flakes:

1. reproduce/isolate the race or nondeterminism
2. fix the test or product behavior
3. quarantine only as a temporary documented exception if absolutely necessary

Do not normalize a red CI pipeline into background decoration.

## Use coverage as evidence, not a game

Codecov tracks coverage, but coverage percentage is not the product goal.

Prioritize:

- changed behavior
- failure paths
- authorization/security boundaries
- data contracts
- regression-prone logic

Do not add meaningless assertions solely to inflate line coverage.

Read `references/fixtures-coverage-and-ci.md` for coverage and CI rules.

## Finish cleanly

Before completing testing work:

- run the smallest relevant test suite during development
- run the repository-required suite before PR completion
- confirm tests fail for the intended regression when practical
- remove accidental network dependencies
- remove sensitive fixture data
- check for flaky timing assumptions
- verify coverage reports are generated where expected
- document any tests that could not be executed and why

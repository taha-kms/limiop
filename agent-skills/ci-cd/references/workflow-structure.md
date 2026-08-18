# Workflow Structure

## Monorepo jobs

Keep ownership clear between frontend, backend, Airflow/data, ML, security/quality, and deployment workflows.

Use reusable workflows or composite actions only when duplication is real and the abstraction makes behavior clearer.

## Triggers

Use `pull_request` for PR validation and protected branch/tag events for post-merge/release work.

Avoid broad triggers that cause deployments or expensive jobs on irrelevant changes.

## Jobs

Keep jobs independently understandable. Name status checks consistently because branch protection may depend on them.

Fail the workflow when a required validation fails; do not hide failures behind `continue-on-error` unless the check is explicitly informational.

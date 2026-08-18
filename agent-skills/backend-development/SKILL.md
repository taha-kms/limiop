---
name: backend-development
description: Develop and modify the SkillSync backend using Python, FastAPI, SQLAlchemy, Pydantic, PostgreSQL, Alembic, and pytest. Use for backend API endpoints, authentication/authorization, application services, persistence, database models and migrations, request/response schemas, configuration, error handling, backend integrations, and backend tests. Apply this skill whenever a task changes files under the SkillSync backend or changes a contract owned by the backend. Follow the repository task workflow and Git rules separately.
---

# SkillSync Backend Development

## Purpose

Implement backend changes without blurring API, business, persistence, pipeline, or ML boundaries. Prefer small, testable changes that fit the existing repository before adding new abstractions.

## Start Every Task

1. Read repository `AGENTS.md` and `docs/PROJECT_CONTEXT.md` before editing.
2. Inspect the relevant backend files, tests, migrations, and established conventions.
3. Follow the repository issue -> branch -> small commits -> pull request workflow.
4. Keep the change within the current issue scope. Create a separate issue for unrelated cleanup or architectural work.
5. Use the installed dependency versions and existing package-management convention. Do not upgrade packages as a side effect of feature work.

## Ownership Boundaries

Keep these responsibilities distinct:

- **Routes/controllers:** HTTP concerns, dependency injection, request parsing, status codes, response models.
- **Schemas:** external API contracts and validation.
- **Services:** application and domain behavior.
- **Models:** SQLAlchemy persistence mapping.
- **Database layer:** sessions, transactions, migrations, database configuration.
- **Clients/integrations:** communication with external systems owned by the backend.
- **Airflow:** scheduled data workflow orchestration; do not move DAG orchestration into FastAPI.
- **ML:** training/evaluation stay outside API routes; backend may call stable inference interfaces.
- **Frontend:** presentation and client interaction; do not move backend rules into UI code.

Read `references/backend-structure.md` when deciding where new code belongs.

## API Rules

- Keep route functions thin. Route handlers should coordinate HTTP input/output, not implement substantial business logic.
- Define explicit request and response schemas. Do not return ORM objects accidentally or expose internal fields by convenience.
- Use FastAPI dependency injection for shared request-scoped concerns such as database sessions and authentication.
- Validate at system boundaries. Treat uploaded CVs, request bodies, query parameters, and external data as untrusted.
- Use appropriate HTTP status codes and stable error responses.
- Avoid leaking stack traces, secrets, database internals, or personal data in responses.
- Prefer resource-oriented URLs and predictable naming. Match existing API conventions before introducing new ones.
- Preserve backward compatibility unless the issue explicitly authorizes a breaking change.

Read `references/api-rules.md` for endpoint design and error-handling details.

## Service Rules

- Put reusable business logic in services or focused domain modules, not route handlers.
- Keep functions small enough to test directly.
- Pass dependencies explicitly where practical rather than reaching through global state.
- Separate orchestration from pure transformations when that improves testability.
- Do not create generic managers, factories, repositories, or base classes without demonstrated duplication or variation.
- Do not use a repository abstraction merely because one might be useful someday. SQLAlchemy can be used directly from focused services when that is the simpler design.

## Database Rules

- Use PostgreSQL as the source-of-truth relational database.
- Use SQLAlchemy models for persistence and Alembic for schema migrations.
- Never change a persistent schema only by editing an ORM model. Add the matching migration.
- Review migrations for data loss, locking risk, nullability transitions, defaults, indexes, and reversibility.
- Prefer database constraints for invariants that the database can enforce reliably.
- Use transactions deliberately. Keep transaction scope understandable and avoid hidden commits inside helper functions.
- Avoid N+1 queries and accidental unbounded result sets.
- Add indexes because a query pattern needs them, not decoratively.
- Never store secrets, large model binaries, or original CV files directly in PostgreSQL.
- Treat destructive migrations as exceptional and require explicit issue scope.

Read `references/database-rules.md` for model and migration guidance.

## Pydantic and Configuration

- Use Pydantic models for API validation and typed configuration where appropriate.
- Keep API schemas separate from database models when their responsibilities differ.
- Do not hardcode secrets or environment-specific URLs.
- Read configuration from environment-backed settings.
- Document new required variables in `.env.example` without real values.
- Fail clearly when required production configuration is missing.

## Authentication and Authorization

- Treat authentication and authorization as separate checks.
- Never trust a user-supplied user ID as proof of ownership.
- Enforce ownership/permission checks server-side before reading or mutating protected resources.
- Hash passwords with an appropriate existing password-hashing mechanism; never store plaintext passwords.
- Keep secrets and tokens out of logs and responses.
- Do not weaken security controls to simplify local development.

## File Uploads and CV Data

CVs contain personal data. Handle them conservatively.

- Validate file type, size, and expected content before processing.
- Do not trust filenames supplied by users for filesystem paths.
- Avoid logging full CV contents or extracted personal information.
- Store original files in object storage when that infrastructure is available; store references/metadata in PostgreSQL.
- Keep parsing failures isolated and return safe, useful errors.
- Delete temporary files after processing when temporary storage is required.

## External Integrations

- Wrap external backend integrations in focused clients/modules.
- Set explicit timeouts.
- Handle unavailable services, malformed responses, rate limits, and partial data.
- Do not retry indefinitely.
- Keep external response shapes out of core application contracts; normalize them at the boundary.
- Do not put scheduled job-source ingestion in request handlers. That belongs to the Airflow/data-engineering side of SkillSync.

## Error Handling and Logging

- Catch exceptions only when the code can add context, translate them into a useful domain/API error, clean up resources, or recover.
- Never use empty broad exception handlers.
- Preserve useful causal information for server-side diagnostics without exposing it to users.
- Use structured/contextual logging where the codebase supports it.
- Never log passwords, tokens, secrets, full CV text, or unnecessary personal information.

## Testing Requirements

Every meaningful backend behavior change needs tests at the lowest useful level.

- Unit-test service/domain behavior and edge cases.
- Test route contracts for status codes, validation, permissions, and response shapes.
- Add database integration tests when behavior depends on PostgreSQL, transactions, constraints, or ORM relationships.
- Add migration checks/tests when the project provides migration test infrastructure.
- Mock only real boundaries. Do not mock the function being tested into irrelevance.
- Cover failure paths, not only the happy path.
- Keep tests deterministic and independent of live external APIs.
- Run the relevant pytest suite before creating the pull request.
- Do not claim a test passed unless it was executed.

Read `references/testing-rules.md` when adding or restructuring backend tests.

## Security and Quality Gates

Backend changes must remain compatible with the repository quality pipeline:

- pytest
- Codecov
- CodeQL
- SonarQube
- Dependabot

Do not silence security or quality findings with blanket exclusions just to make CI green. Fix findings related to the change when reasonable; track unrelated larger work separately.

## Completion Check

Before finishing a backend task, verify:

- Code is in the correct layer.
- API contracts are explicit.
- Database changes include migrations where required.
- Authorization is enforced server-side where required.
- External/user input is validated.
- Errors and logs do not expose sensitive data.
- Tests cover changed behavior and important failure cases.
- Relevant tests and checks were actually run.
- No unrelated refactor, dependency upgrade, generated artifact, secret, or user data entered the change.
- Git/GitHub activity follows `AGENTS.md`, including short human-style one-line commits and no agent/model/vendor identity.

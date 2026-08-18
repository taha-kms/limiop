# SkillSync Agent Instructions

## 1. Purpose

This file defines how coding agents must work inside the **SkillSync** repository.

All agents must follow these rules regardless of which model, vendor, editor, CLI, IDE, or automation environment is being used.

Before making changes, read:

```text
docs/PROJECT_CONTEXT.md
```

That document defines what SkillSync is, its architecture, technology stack, responsibilities, and project boundaries.

This file defines **how work must be performed**.

---

# 2. Core Working Principles

When modifying SkillSync:

1. Understand the requested change before editing code.
2. Inspect the existing implementation first.
3. Make the smallest reasonable change.
4. Preserve existing architecture unless the task explicitly requires architectural work.
5. Keep changes focused.
6. Add or update tests for meaningful behavior changes.
7. Validate changes before committing.
8. Work through GitHub issues, branches, commits, and pull requests.
9. Never make unrelated cleanup changes inside a task.
10. Never silently redesign working parts of the system.

Prefer incremental development over large rewrites.

---

# 3. Mandatory GitHub Workflow

Every meaningful development task must follow this lifecycle:

```text
Issue
  ↓
Small branch
  ↓
Implementation
  ↓
Tests
  ↓
Small commits
  ↓
Push branch
  ↓
Pull request
  ↓
Review / CI
  ↓
Merge
```

Do not skip directly from a task request to modifying the default branch.

---

# 4. Issue-First Development

Before implementing a meaningful change, there must be a GitHub issue describing the work.

If an appropriate issue already exists:

* use the existing issue
* read its description and discussion
* keep the implementation within its scope

If no issue exists and GitHub write access is available:

* create a new issue before implementation

An issue should be concise and useful.

Recommended structure:

```markdown
## Problem

Describe what needs to change and why.

## Scope

Describe the work included in this issue.

## Acceptance Criteria

- Expected behavior 1
- Expected behavior 2
- Tests pass
```

Do not create enormous issue descriptions for simple work.

A small task should have a small issue.

Example:

```text
Add health-check endpoint
```

is preferable to:

```text
Comprehensive backend operational observability and
availability verification infrastructure implementation
```

Write like a developer, not a procurement department.

---

# 5. Keep Issues Focused

Prefer:

```text
Issue #21 - Add job source model
Issue #22 - Add Arbeitnow ingestion client
Issue #23 - Add job normalization
Issue #24 - Add ingestion DAG
```

instead of:

```text
Issue #21 - Build the entire data platform
```

Each issue should represent one coherent, reviewable change.

If a task becomes too large, split it into smaller issues.

---

# 6. Branch Rules

Never implement normal development work directly on:

```text
main
master
develop
```

or another protected/default branch.

Create a dedicated branch for each issue.

Preferred naming pattern:

```text
<type>/<issue-number>-<short-description>
```

Examples:

```text
feat/21-job-source-model
feat/22-arbeitnow-client
fix/31-cv-upload-validation
test/44-job-matching-tests
docs/52-airflow-architecture
refactor/63-job-normalizer
ci/71-codecov-workflow
```

Allowed common prefixes include:

```text
feat/
fix/
refactor/
test/
docs/
ci/
chore/
```

Branch names must be:

* short
* descriptive
* lowercase
* hyphen-separated
* related to the issue

Do not include personal names, agent names, vendor names, company names, or model names in branch names.

---

# 7. One Branch, One Purpose

A branch should address one issue or one tightly related unit of work.

Do not mix unrelated changes.

Bad:

```text
feat/21-job-ingestion
```

containing:

* job ingestion
* navbar redesign
* authentication changes
* dependency upgrades
* README rewrite

Good:

```text
feat/21-job-ingestion
```

containing only the work required for job ingestion.

If unrelated work is discovered, create another issue.

---

# 8. Small Changes

Prefer small, reviewable changes.

Avoid implementing a large feature in one giant change when it can reasonably be divided.

For example, instead of:

```text
Build complete recommendation system
```

prefer separate work such as:

```text
Add job embeddings
Add CV embeddings
Add cosine similarity service
Add match-score endpoint
Add recommendation tests
```

Small changes make debugging, reviewing, reverting, and testing easier.

---

# 9. Commit Rules

Commits must be small and focused.

Each commit should represent one logical change.

Examples:

```text
Add job source model
Add Arbeitnow API client
Handle missing job locations
Add job normalization tests
Fix duplicate job detection
Update Airflow ingestion DAG
```

Commit messages must:

* be short
* be one line
* sound naturally written by a developer
* describe the actual change
* use clear language
* match the size of the commit

Do not write multi-paragraph commit messages.

Do not write essays.

Do not add unnecessary explanations to commit messages.

Do not include generated summaries of every changed file.

---

# 10. Commit Message Style

Prefer simple imperative-style messages.

Good:

```text
Add job matching endpoint
Fix CV parsing error
Update job schema
Add Airflow ingestion tests
Remove unused skill mapper
```

Also acceptable when useful:

```text
feat: add job matching endpoint
fix: handle empty CV uploads
test: cover job normalization
ci: add Codecov reporting
```

Keep whichever convention is already established in the repository.

Do not invent a new commit convention when the repository already has one.

---

# 11. Commit Messages Must Stay Human

Do not produce messages such as:

```text
Implement comprehensive job matching functionality with
enhanced semantic analysis and robust error handling
```

Do not produce:

```text
Updated files:
- backend/app/services/matching.py
- backend/app/models/job.py
- tests/test_matching.py

This commit introduces...
```

Do not produce:

```text
Implement job matching system

- Add embedding support
- Add matching endpoint
- Add validation
- Add tests
- Update configuration
```

Instead, split the work when necessary:

```text
Add embedding service
Add job match endpoint
Add matching tests
```

Small commits should have small messages.

---

# 12. No AI or Agent Identity in Git Operations

This rule is strict.

Never include the identity of an AI system, coding agent, model, vendor, or model provider in any Git or GitHub activity performed for SkillSync.

This includes:

* commit messages
* commit bodies
* branch names
* tag names
* pull request titles
* pull request descriptions
* issue titles
* issue descriptions
* issue comments
* pull request comments
* review comments
* release notes
* Git trailers
* co-author fields
* author fields created by the agent
* merge messages
* Git notes

Do not include names or references such as:

```text
Claude
Codex
ChatGPT
GPT
OpenAI
Anthropic
Gemini
Copilot
AI-generated
generated by AI
created by an agent
assisted by AI
```

or equivalent references to any current or future AI model, company, vendor, or coding assistant.

The repository history should describe **the engineering work**, not which tool helped perform it.

---

# 13. Git Identity

Use the Git identity already configured for the repository or development environment.

Do not modify:

```text
git config user.name
git config user.email
```

unless explicitly instructed by the repository owner.

Never configure Git identity to an AI model, tool, vendor, or fabricated human identity.

Never add AI-related `Co-authored-by` trailers.

Do not forge authorship.

---

# 14. Pull Requests Are Required

After completing work on a branch:

1. run the relevant tests
2. run required linting and validation
3. review the diff
4. push the branch
5. create a pull request

Do not merge directly unless explicitly requested and repository permissions allow it.

---

# 15. Pull Request Scope

A pull request should normally correspond to one issue.

The PR should:

* have a concise title
* describe what changed
* explain anything non-obvious
* mention relevant testing
* reference the issue

Example title:

```text
Add Arbeitnow job ingestion
```

Example body:

```markdown
## Summary

Adds the initial Arbeitnow job ingestion client and maps API results to the internal job schema.

## Testing

- Added client tests
- Added normalization tests
- Verified API response handling

Closes #22
```

Keep PR descriptions proportional to the work.

Do not generate lengthy PR narratives for trivial changes.

---

# 16. Never Mention the Coding Agent in Pull Requests

Pull requests must not contain statements such as:

```text
Generated by...
Implemented by...
AI-assisted...
Created using...
Agent changes...
```

Describe:

```text
what changed
why it changed
how it was tested
```

Nothing more is required.

---

# 17. Review Before Commit

Before committing:

* inspect `git diff`
* confirm only intended files changed
* remove debugging code
* remove temporary files
* remove commented-out experiments
* verify no secrets are present
* verify generated artifacts are appropriate to commit
* run relevant tests

Do not blindly commit every modified file.

Stage intentionally.

Prefer:

```text
git add backend/app/services/job_ingestion.py
git add tests/test_job_ingestion.py
```

over automatically staging unrelated repository changes.

---

# 18. Never Commit Secrets

Never commit:

```text
.env
API keys
access tokens
private keys
database passwords
AWS credentials
JWT secrets
production credentials
real user CV files
production datasets
```

Use:

```text
.env.example
```

for documenting required environment variables.

Example:

```text
DATABASE_URL=
JWT_SECRET=
ARBEITNOW_BASE_URL=
S3_BUCKET=
```

Never place real values inside `.env.example`.

---

# 19. Dependency Rules

Do not add a dependency simply because it makes a small task slightly easier.

Before adding a dependency:

1. check whether the existing stack already solves the problem
2. verify the dependency is maintained
3. confirm it is appropriate for the project
4. add it using the project's dependency-management convention
5. update lock files where applicable
6. add tests where necessary

Avoid overlapping libraries that solve the same problem.

For example, do not introduce three HTTP clients when one already exists.

---

# 20. Dependabot

Dependabot is part of SkillSync's dependency maintenance strategy.

Do not disable or bypass Dependabot without an explicit reason.

Dependabot-generated branches and pull requests are external automated dependency-management operations and are not subject to the agent-identity naming restriction above.

When reviewing or modifying Dependabot PRs, still follow normal testing and quality requirements.

---

# 21. Architecture Boundaries

Follow the architecture defined in:

```text
docs/PROJECT_CONTEXT.md
```

In particular:

### Frontend

Frontend code should handle:

* presentation
* client interaction
* frontend state
* API consumption

Do not place:

* direct PostgreSQL queries
* Airflow orchestration
* ML training logic
* backend business rules

inside frontend components.

### Backend

FastAPI should handle:

* APIs
* business logic
* authentication
* validation
* persistence coordination
* ML inference integration

Avoid putting complex business logic directly inside route handlers.

Use services/modules where appropriate.

### Airflow

Airflow should orchestrate workflows.

DAG files should remain thin.

Avoid implementing large transformation functions directly inside DAG definitions.

Prefer:

```text
DAG
 ↓
Reusable Python service
 ↓
Transformation
```

rather than:

```text
DAG containing hundreds of lines of processing logic
```

### Machine Learning

Separate:

```text
training
evaluation
inference
```

Do not mix notebooks or experiments directly into production API code.

---

# 22. Database Changes

Schema changes must be intentional.

When changing database models:

* update ORM models
* update schemas where necessary
* create/update migrations when migrations are available
* update affected tests
* consider backward compatibility
* avoid destructive changes without explicit justification

Do not manually modify production databases as part of normal application development.

---

# 23. Testing Requirements

Every meaningful behavior change should have appropriate tests.

Examples:

Backend logic:

```text
pytest
```

Frontend behavior:

```text
Playwright
```

Data pipelines:

* unit-test transformations
* validate source parsing
* test normalization
* test deduplication behavior
* test expected failure cases

Machine learning:

* test preprocessing
* test input/output contracts
* evaluate models using defined metrics
* avoid treating successful execution as model validation

---

# 24. Test Before Pull Request

Before creating a pull request, run the tests relevant to the changed area.

If the repository provides standard commands, use them.

Do not claim tests passed unless they were actually executed.

If a test cannot be run because of an environment limitation, state that clearly in the PR.

---

# 25. Code Coverage

Codecov is used to monitor test coverage.

New code should be tested meaningfully.

Do not write meaningless tests solely to increase the coverage number.

Prioritize behavior and failure cases.

---

# 26. Code Quality

SonarQube is used for code-quality analysis.

Avoid introducing:

* duplicated logic
* unnecessarily complex functions
* dead code
* unused imports
* unreachable code
* unclear naming
* excessive nesting

Fix quality issues related to the current change when reasonable.

Do not turn a small feature PR into an unrelated repository-wide cleanup.

---

# 27. Security

CodeQL is used for static security analysis.

Treat security findings seriously.

Pay particular attention to:

* authentication
* authorization
* file uploads
* CV processing
* SQL/database access
* external API data
* HTML rendering
* secrets
* path handling
* user-controlled input

Never assume external job descriptions or uploaded CVs are trusted input.

---

# 28. External Data Is Untrusted

Job APIs, uploaded CVs, ESCO data, and other external sources must be treated as untrusted input.

Validate data before using or storing it.

Handle:

* missing fields
* unexpected types
* malformed responses
* duplicate records
* invalid URLs
* unexpected HTML
* encoding problems
* source outages

Do not assume APIs always return ideal data.

They are APIs. Optimism has consequences.

---

# 29. Error Handling

Handle expected failures explicitly.

Avoid:

```python
except Exception:
    pass
```

Do not silently swallow errors.

Provide enough logging and context to diagnose failures without exposing secrets or personal information.

---

# 30. Logging

Logs should help diagnose system behavior.

Do not log:

* passwords
* tokens
* full CV contents
* authentication credentials
* secret environment variables
* unnecessary personal user information

Use appropriate log levels.

---

# 31. Documentation

Update documentation when a change affects:

* setup
* architecture
* public APIs
* environment variables
* local development
* deployment
* data pipelines
* important workflows

Do not rewrite unrelated documentation while completing a small feature.

---

# 32. Avoid Premature Abstraction

Do not create abstractions for hypothetical future requirements.

Prefer working code with clear boundaries.

Refactor when repeated patterns or genuine complexity justify it.

Do not create:

```text
BaseAbstractGenericJobProviderFactoryManager
```

when a small interface and two implementations will do.

---

# 33. No Unrequested Large Refactors

If a requested task exposes architectural problems, do not silently rewrite large parts of the repository.

Instead:

1. complete the requested task safely if possible
2. create a separate issue describing the larger improvement

Large refactors deserve their own issue, branch, tests, and PR.

---

# 34. Preserve Existing Work

Before editing a file:

* read it
* understand its purpose
* inspect related files where necessary

Do not overwrite existing implementations without understanding them.

Do not delete code simply because another approach appears cleaner.

---

# 35. Generated Files

Do not commit generated files unless they belong in version control.

Examples that normally should not be committed:

```text
node_modules/
__pycache__/
.pytest_cache/
coverage/
dist/
build/
.env
local databases
temporary datasets
model binaries
uploaded CVs
```

Follow `.gitignore`.

---

# 36. Agent Task Completion Checklist

Before considering a development task complete, verify:

* [ ] Relevant project context was read
* [ ] GitHub issue exists
* [ ] Dedicated branch was created
* [ ] Branch is focused on one issue
* [ ] Existing code was inspected before modification
* [ ] Implementation follows project architecture
* [ ] Tests were added or updated where appropriate
* [ ] Relevant tests were run
* [ ] No secrets or user data were committed
* [ ] Diff was reviewed
* [ ] Commits are small and focused
* [ ] Commit messages are short and one-line
* [ ] No AI/model/vendor identity appears in Git activity
* [ ] Branch was pushed
* [ ] Pull request was created
* [ ] PR references the relevant issue
* [ ] PR explains testing performed
* [ ] CI results are checked when available

---

# 37. Default Development Pattern

Unless the task requires otherwise, use this sequence:

```text
Read project context
       ↓
Understand request
       ↓
Inspect relevant code
       ↓
Find existing issue
       ↓
Create issue if needed
       ↓
Create small branch
       ↓
Implement smallest useful change
       ↓
Add/update tests
       ↓
Run validation
       ↓
Review diff
       ↓
Create small commit(s)
       ↓
Push branch
       ↓
Create pull request
       ↓
Check CI
```

This is the default workflow for SkillSync development.

---

# 38. Final Rule

Optimize for a repository history that another experienced developer can understand.

Issues should explain why work exists.

Branches should show what is being worked on.

Commits should show small steps.

Pull requests should show complete reviewable changes.

The history should never reveal or depend on which coding assistant performed the work.

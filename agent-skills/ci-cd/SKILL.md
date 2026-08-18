---
name: ci-cd
description: Develop and modify SkillSync continuous integration, continuous delivery, and repository automation. Use whenever work changes GitHub Actions workflows, Codecov integration, CodeQL scanning, SonarQube analysis or quality gates, Dependabot, Docker build automation, deployment pipelines, environment protections, CI caching/concurrency, workflow permissions, release automation, or required status checks. Keep pipelines fast, reproducible, least-privileged, monorepo-aware, and aligned with SkillSync's issue/branch/PR workflow.
---

# SkillSync CI/CD

## Start with repository rules

Before changing automation:

1. Read `AGENTS.md` and `docs/PROJECT_CONTEXT.md`.
2. Inspect `.github/workflows/`, Dependabot configuration, Dockerfiles, coverage configuration, Sonar configuration, and deployment docs.
3. Follow the repository issue/branch/commit/PR workflow.
4. Preserve existing required status-check names unless intentionally migrating branch protection.

## Treat CI as a product contract

A pull request should answer, automatically where practical:

- does the code lint/type-check?
- do relevant tests pass?
- does the affected application build?
- does coverage remain acceptable?
- do security/code-quality gates pass?
- is the change deployable?

Do not create duplicate workflows that perform the same checks with slightly different names.

## Keep monorepo workflows scoped

SkillSync contains frontend, backend, Airflow/data, ML, and shared infrastructure.

Use path-aware jobs/workflows where this reduces unnecessary work without making required cross-cutting checks disappear.

Typical workflow ownership may include:

- frontend CI
- backend CI
- Airflow/data CI
- ML CI
- code/security analysis
- deployment

Read `references/workflow-structure.md` for monorepo and job design.

## Define PR quality gates

Require the relevant combination of:

- formatting/linting
- type checking
- unit/integration tests
- build validation
- coverage upload/status
- SonarQube analysis/quality gate
- CodeQL/code scanning

Do not require unrelated heavyweight jobs on every tiny change if path-aware gating can preserve safety.

Codecov is a signal about coverage; SonarQube is a quality/security analysis gate; CodeQL is code security analysis. Do not treat one tool as a substitute for the others.

Read `references/quality-gates.md` for gate behavior.

## Secure GitHub Actions

Use least-privilege `permissions` for `GITHUB_TOKEN` and jobs.

Prefer immutable full commit SHA pins for third-party actions when practical, with a human-readable version comment if the repository adopts that convention.

Do not expose secrets to pull requests from untrusted forks.

Avoid `pull_request_target` with checkout/execution of untrusted PR code unless the workflow is specifically designed and reviewed for that threat.

Do not interpolate untrusted event data directly into shell scripts.

Use GitHub environments/environment protections for sensitive deployments when available.

Read `references/workflow-security.md` before changing permissions, secrets, reusable workflows, or deployment credentials.

## Keep secrets out of workflow files

Store secrets in the platform's secrets/environment system.

Do not hardcode:

- deployment tokens
- cloud credentials
- database credentials
- Sonar tokens
- signing keys
- private registry credentials

Prefer short-lived/federated credentials over long-lived cloud keys when the chosen deployment platform supports them.

## Build once when practical

Separate build/test from deployment.

Prefer promoting a verified immutable image/artifact rather than rebuilding different bits for each environment.

Tag Docker images/artifacts with immutable identifiers such as commit SHA in addition to any friendly environment/release tags.

Do not deploy source that did not pass the required checks.

## Keep deployments controlled

For normal feature PRs:

```text
pull request -> CI/security/quality checks -> review -> merge
```

For deployment:

```text
protected branch/tag -> verified artifact -> environment gate -> deploy -> health verification
```

Do not let pull requests from arbitrary forks deploy production resources.

Do not place production deployment credentials in generic test jobs.

Read `references/deployment-and-release.md` for deployment rules.

## Use concurrency deliberately

Cancel obsolete PR runs where safe to save CI capacity.

Do not cancel migration/deployment jobs mid-operation unless the workflow is designed to tolerate it.

Prevent two production deployments from racing each other through environment/concurrency controls.

## Cache safely

Cache dependency/download state, not secrets or mutable production artifacts.

Key caches from lockfiles and relevant runtime/tool versions.

Do not let cache correctness become a hidden prerequisite for a successful clean build.

## Configure Dependabot deliberately

Monitor at least the dependency ecosystems actually present in the monorepo, which may include:

- npm
- Python
- GitHub Actions
- Docker

Keep update cadence and grouping manageable. Do not auto-merge dependency changes without passing the same meaningful tests/security checks required for comparable human PRs.

Read `references/dependencies-and-maintenance.md` for dependency-update rules.

## Integrate Codecov without gaming coverage

Upload coverage only after tests actually complete.

Use project/patch coverage statuses according to repository policy.

Do not suppress real coverage regressions by excluding newly added production code merely to make a check green.

## Integrate SonarQube as a quality gate

Run analysis on the code/configuration appropriate to the monorepo.

Treat a configured Sonar quality gate as a merge signal. Fix current-change issues where reasonable instead of disabling rules to silence the pipeline.

Avoid turning a small task into unrelated repository-wide quality cleanup.

## Integrate CodeQL/code scanning

Use GitHub-supported CodeQL setup appropriate to the repository and plan.

Keep languages/build mode aligned with the code actually present.

Do not duplicate default and advanced CodeQL setups in ways that conflict or waste CI.

## Verify workflow changes

Before completing CI/CD changes:

- validate YAML
- review workflow triggers
- review permissions
- review secret exposure paths
- check path filters
- check cache keys
- check failure propagation
- test locally where tooling supports it
- inspect a real workflow run when repository access allows
- verify required checks/deployments behave as intended

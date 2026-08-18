---
name: task-workflow
description: Execute development work in the SkillSync repository through the required issue-first GitHub workflow. Use for any SkillSync feature, bug fix, refactor, test, documentation, database, frontend, backend, Airflow, ML, CI/CD, or security change that modifies repository content. Inspect project context first, create or reuse a focused issue, work on a small dedicated branch, make small human-style one-line commits, run relevant checks, push, and open a linked pull request. Enforce SkillSync Git hygiene and never place coding-agent, model, vendor, or provider identity in Git or GitHub activity.
---

# SkillSync Task Workflow

## Objective

Execute SkillSync development tasks as small, reviewable GitHub changes. Treat the repository history as an engineering record, not a transcript of the tool that produced it.

## Required Inputs

Accept one of the following:

- a natural-language development task;
- an existing GitHub issue number or URL;
- a bug report, feature request, refactor request, test request, documentation request, or CI task.

Require access to the SkillSync repository and a working GitHub write path through the environment's native GitHub integration or `gh` CLI. If GitHub write access is unavailable, do not invent issue numbers, PRs, or successful pushes. Report the exact blocked operation.

## Required Repository Context

Before planning or editing code:

1. Read `AGENTS.md` from the repository root.
2. Read `docs/PROJECT_CONTEXT.md`.
3. Inspect the files relevant to the task.
4. Inspect nearby tests, configuration, and established conventions.
5. Check the current branch and working tree before changing anything.

Treat `AGENTS.md` as the repository operating contract and `docs/PROJECT_CONTEXT.md` as the architectural source of truth.

If either required file is missing, report it before proceeding with a normal implementation task. Do not silently substitute invented project rules.

## Workflow

Follow this sequence for every meaningful repository change:

1. Understand and scope the task.
2. Find an existing GitHub issue that matches the task.
3. Create a focused issue if no suitable issue exists.
4. Create a small branch tied to that issue.
5. Implement only the issue scope.
6. Add or update appropriate tests.
7. Run relevant local validation.
8. Review the diff and working tree.
9. Create small, focused commits with short one-line messages.
10. Push the branch.
11. Open a pull request linked to the issue.
12. Check available CI results and address failures caused by the change.
13. Report the issue, branch, commits, tests, and PR accurately.

Do not skip issue creation, branch creation, or PR creation merely because the code change is small. Documentation and CI changes are still repository work unless the user explicitly requests a non-GitHub exception.

## Scope the Issue

Keep one issue focused on one coherent outcome.

Prefer several small issues over one broad issue when a request contains independently reviewable work. Execute separate issues on separate branches rather than accumulating unrelated work on one branch.

Use a concise issue structure:

```markdown
## Problem
<what needs to change and why>

## Scope
<what this issue includes>

## Acceptance Criteria
- <observable outcome>
- <relevant tests or validation pass>
```

Keep simple issues simple. Do not turn a small implementation task into a project proposal.

## Create the Branch

Create branches from the repository's current intended base branch after confirming it is up to date enough for the task.

Use this pattern unless the repository already establishes a compatible convention:

```text
<type>/<issue-number>-<short-description>
```

Use prefixes such as `feat`, `fix`, `refactor`, `test`, `docs`, `ci`, or `chore`.

Examples:

```text
feat/21-job-source-model
fix/31-cv-upload-validation
ci/48-codecov-reporting
```

Keep branch names lowercase, short, and hyphen-separated.

Never work directly on a protected/default branch for ordinary development work.

## Keep Changes Small

Implement the smallest complete change that satisfies the issue.

Do not:

- bundle unrelated cleanup;
- rewrite working architecture without an issue requiring it;
- add speculative abstractions;
- introduce unrelated dependencies;
- reformat unrelated files;
- fix unrelated warnings just because they are nearby.

When new unrelated work is discovered, create a separate issue rather than expanding the current branch.

## Commit Discipline

Create small commits that each represent one logical step.

Write commit messages as a human developer would write them:

- use one line only;
- keep the message short;
- describe the actual change;
- prefer simple imperative wording;
- follow an established repository convention if one exists;
- keep a small commit paired with a small message.

Good examples:

```text
Add job source model
Handle empty CV uploads
Add job normalization tests
Update ingestion schedule
```

Do not use multi-line commit messages, generated summaries, file-by-file narratives, promotional wording, or inflated descriptions.

Before each commit:

1. inspect the diff;
2. stage intentionally;
3. ensure the staged files belong to the same logical change;
4. confirm no secrets, real CVs, local data, model binaries, or accidental generated files are staged.

## Identity Prohibition

Never include the identity of a coding assistant, model, vendor, provider, or AI system in Git or GitHub activity.

Apply this prohibition to:

- issue titles and bodies;
- issue comments;
- branch names;
- commit subjects and bodies;
- commit trailers;
- author or co-author metadata created by the agent;
- tag names;
- pull request titles and bodies;
- PR comments and review comments;
- merge messages;
- release notes;
- Git notes.

Do not describe work as AI-generated, agent-generated, assistant-generated, or machine-generated.

Do not add automated attribution, signatures, promotional footers, or co-author trailers identifying the tool that performed the work.

Use the Git identity already configured in the environment. Never modify `user.name` or `user.email` unless the repository owner explicitly instructs it. Never invent a human identity.

Before every GitHub write and commit, review the text for accidental tool/vendor/model attribution and remove it.

## Testing and Validation

Run the checks relevant to the changed area. Follow repository-provided commands when available.

At minimum:

- run unit tests affected by backend or library changes;
- run frontend tests for changed UI behavior;
- run pipeline/data tests for changed transformations or ingestion logic;
- run linting/type checks applicable to edited code;
- verify migrations when database schema changes;
- validate workflow/config syntax when CI/CD changes.

Do not claim a check passed unless it actually ran successfully.

If a required check cannot run because of an environment limitation, state exactly which check was not run and why in the PR.

## Review Before Push

Before pushing:

1. inspect `git status`;
2. inspect the final branch diff against the base branch;
3. confirm the branch contains only issue-related work;
4. confirm commit messages are short and one-line;
5. confirm no forbidden identity attribution exists in Git metadata or GitHub text;
6. confirm relevant tests have run;
7. confirm no secrets or personal data are present.

Never force-push unless explicitly required and safe for the current branch. Never rewrite another contributor's history without explicit instruction.

## Open the Pull Request

Create one pull request for the branch and link it to the issue.

Use a concise human-written title. Keep the body proportional to the change.

Use this structure when useful:

```markdown
## Summary
<what changed and why>

## Testing
- <test or validation actually run>

Closes #<issue-number>
```

Do not claim CI is green until the relevant checks actually report success.

Do not merge the PR unless the user or repository workflow explicitly authorizes merging.

## CI Follow-up

Inspect available GitHub checks after opening the PR.

For failures caused by the branch:

1. inspect the failure;
2. fix only the relevant problem;
3. rerun the appropriate validation;
4. commit the fix with a short one-line message;
5. push to the same issue branch;
6. re-check CI.

Respect SkillSync's configured quality and security systems, including GitHub Actions, Codecov, CodeQL, SonarQube, and Dependabot.

Do not disable quality gates merely to make the PR pass.

## GitHub Interface

Use the environment's supported GitHub write mechanism. Prefer a connected/native GitHub integration when it can perform the required action; otherwise use authenticated `gh` commands.

Do not mix multiple write mechanisms unnecessarily within one task.

Before GitHub writes, verify the target repository, issue, branch, and base branch to avoid writing to the wrong repository.

## Completion Report

At the end of the task, report only verified facts:

- issue number/title;
- branch name;
- concise implementation summary;
- tests and checks actually run;
- commit subjects;
- pull request number/title or URL when available;
- remaining CI failures or blockers, if any.

Do not include tool identity or attribution in the completion report if that report will be copied into GitHub activity.

## Exceptions

Allow deviation from the issue/branch/PR workflow only when the user explicitly requests an exception for the current task or when GitHub access prevents the required operation.

Never silently downgrade the workflow.

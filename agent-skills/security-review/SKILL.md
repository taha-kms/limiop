---
name: security-review
description: Perform security-focused review and implement security fixes for SkillSync across Next.js, FastAPI, PostgreSQL, CV/file handling, external job ingestion, Airflow, ML/data processing, Docker, dependencies, and GitHub Actions. Use for threat modeling, security review of PRs or designs, authentication/authorization checks, input/file validation, secrets handling, injection/SSRF/XSS/CORS risks, supply-chain and CI security, privacy-sensitive CV data, CodeQL/Sonar findings, or remediation work. Use OWASP ASVS as a verification baseline and current OWASP web-risk guidance while prioritizing concrete exploit paths over generic checklists.
---

# SkillSync Security Review

## Begin with the system and change

Before reviewing security:

1. Read `AGENTS.md` and `docs/PROJECT_CONTEXT.md`.
2. Identify the exact change, data flow, trust boundaries, and exposed surfaces.
3. Inspect surrounding code and configuration rather than reviewing a diff in isolation.
4. Determine what sensitive assets are involved: accounts, CVs, parsed personal data, tokens, database records, model artifacts, deployment credentials, or external integrations.
5. Follow the repository task/Git workflow for any remediation changes.

## Use risk-based review

Use OWASP ASVS as a concrete verification baseline and the current OWASP Top 10 as an awareness checklist.

Do not claim the application is "secure" because a checklist or scanner passes.

Prioritize exploitable paths and impact.

Read `references/threat-model-and-review.md` for the review method.

## Review authentication and authorization first

For private user resources, verify authorization on the trusted server side for every operation.

Check ownership/permission on:

- CV retrieval/update/delete
- saved jobs
- job match results tied to a user
- profile/account operations
- administrative or pipeline operations if exposed

Do not accept a user-supplied `user_id` as authorization proof.

Deny access by default except for intentionally public resources.

Read `references/auth-and-web-security.md` for authentication, authorization, sessions/tokens, CORS, CSRF, XSS, and injection review.

## Treat CV upload as a hostile file boundary

Uploaded CVs are untrusted.

Validate:

- size limits
- allowed types/content
- parser behavior
- filename/path handling
- storage location and access permissions
- decompression/resource-exhaustion risks where relevant

Do not execute uploaded content.

Do not store uploaded files in publicly executable server paths.

Do not trust MIME type or filename extension alone.

Keep parsing isolated from shell commands and arbitrary path construction.

Read `references/files-data-and-privacy.md` for CV and personal-data rules.

## Treat external job data as untrusted

Job descriptions, company fields, URLs, HTML, and provider payloads are attacker-controlled from SkillSync's perspective.

Review for:

- stored/reflected XSS
- unsafe HTML rendering
- open redirects
- malicious apply URLs
- SSRF if the server fetches user/provider-controlled URLs
- parser injection
- oversized payloads
- schema confusion

Never render provider HTML unsanitized in the frontend.

Prefer allowlisted URL schemes and explicit outbound-fetch rules.

## Prevent injection

Use parameterized SQL/SQLAlchemy expressions rather than string-built SQL with untrusted values.

Avoid shell construction with untrusted data.

Validate and encode at the correct boundary for HTML/URL/command contexts.

Do not rely on frontend validation for server security.

## Review secrets and sensitive data

Never commit or log secrets.

Review:

- `.env` handling
- GitHub Actions secrets
- database URLs
- JWT/session secrets
- cloud/object-storage credentials
- Sonar/Codecov/deployment tokens

If a secret is discovered in Git history, treat rotation/revocation as necessary; deleting the visible line alone does not invalidate the credential.

Use GitHub secret protection/scanning where available to prevent or detect accidental pushes.

## Review CI/CD and supply chain

Treat build pipelines as privileged code.

Check:

- GitHub Actions permissions
- third-party action pinning
- untrusted PR execution
- secret exposure
- dependency update policy
- package lockfiles
- Docker base images
- build provenance where introduced

CodeQL, SonarQube, and Dependabot are inputs to review, not substitutes for review.

Read `references/ci-and-supply-chain.md` for CI/supply-chain checks.

## Review database security

Check:

- authorization before data access
- parameterized queries
- least-privilege database credentials
- sensitive logging
- destructive query exposure
- tenant/user ownership filters
- backups/dumps containing personal data

Do not expose raw database errors containing secrets or internals to clients.

## Review API behavior

Check:

- request-size limits where needed
- rate/abuse controls on expensive endpoints
- authentication failure behavior
- authorization object ownership
- predictable error responses without sensitive internals
- CORS policy
- redirect handling
- pagination/resource exhaustion

Pay particular attention to CV parsing, matching endpoints, and any endpoint that triggers expensive ML or pipeline work.

## Review Airflow and data pipelines

Airflow should not expose broad administrative capabilities publicly.

Review:

- connections/secrets
- DAG parameters
- external payload handling
- SQL construction
- task command execution
- object-storage paths
- logs containing CV/personal data

Do not put secrets directly in DAG source.

Treat historical raw provider payloads as untrusted stored content.

## Review ML-specific risks realistically

For SkillSync's initial local/baseline ML stack, focus on:

- untrusted text input
- artifact integrity/versioning
- unsafe model deserialization
- resource exhaustion
- leakage of CV text into logs/artifacts
- unauthorized reuse of user CVs for training

Do not invent exotic model-security systems before the actual architecture requires them.

Never load untrusted pickle/joblib-style artifacts from arbitrary users or URLs.

## Rank findings

For each real finding, provide:

- severity
- affected component/file
- exploit/precondition
- impact
- concrete remediation
- test/verification needed

Distinguish:

- confirmed vulnerability
- likely vulnerability requiring validation
- hardening recommendation

Do not inflate minor hardening suggestions into critical findings.

Read `references/finding-format.md` for review output.

## Verify fixes

For security fixes:

- add a regression test where practical
- rerun relevant unit/integration/e2e tests
- rerun relevant static/security checks
- verify the vulnerable path is actually blocked
- check adjacent equivalent paths

Do not close a security issue merely because a scanner no longer reports it if the exploit path remains.

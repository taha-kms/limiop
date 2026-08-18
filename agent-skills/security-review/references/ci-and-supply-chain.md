# CI and Supply Chain

Review GitHub Actions as privileged code.

Check:

- minimal `GITHUB_TOKEN` permissions
- immutable pinning of third-party actions where practical
- whether untrusted PR code can access secrets
- `pull_request_target` misuse
- shell interpolation of event fields
- deployment environment protections
- dependency lockfiles
- Dependabot/security alerts
- CodeQL and Sonar findings

Do not auto-merge dependency changes purely because they were opened by automation. Run normal relevant checks and review high-risk upgrades.

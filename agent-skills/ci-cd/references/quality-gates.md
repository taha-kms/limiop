# Quality Gates

A merge gate should reflect risk, not tool count.

Typical relevant checks:

- lint/format
- type checks
- tests
- application/Docker build
- Codecov status
- SonarQube quality gate
- CodeQL/code scanning

Do not duplicate the same static-analysis responsibility merely to collect badges.

If a required external service is unavailable, fail or clearly mark the check according to repository policy. Do not report success for analysis that never ran.

# Workflow Security

- Declare minimal `permissions` for jobs/workflows.
- Prefer full commit SHA pins for third-party actions where practical.
- Keep secrets out of logs and command echoing.
- Never pass production secrets to untrusted fork code.
- Treat PR titles, branch names, commit messages, issue text, and other event fields as untrusted strings.
- Avoid executing untrusted event content in shell expressions.
- Review `pull_request_target` very carefully; do not checkout and run untrusted PR code with elevated secrets/permissions.
- Prefer environment-scoped deployment credentials.
- Prefer short-lived cloud identity federation when supported.

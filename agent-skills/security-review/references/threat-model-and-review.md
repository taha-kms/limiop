# Threat Model and Review

For the changed feature, identify:

1. assets: what is valuable/sensitive?
2. actors: anonymous user, authenticated user, malicious provider payload, compromised dependency, CI contributor
3. entry points: API, browser, upload, external URL, DAG input, workflow event
4. trust boundaries: browser/backend, backend/database, pipeline/provider, CI/secrets, storage/parser
5. abuse paths: unauthorized read/write, injection, resource exhaustion, data leakage, credential theft, malicious file/content

Review the highest-impact plausible paths first.

Use automated findings as leads. Confirm exploitability/context before assigning severity.

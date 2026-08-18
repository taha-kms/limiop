# Source Ingestion Rules

## Contents

1. Adapter boundary
2. Network behavior
3. Pagination
4. Attribution and URLs
5. Schema drift
6. Failure handling
7. Fixtures

## 1. Adapter Boundary

Create one focused adapter/client per external source.

A source adapter should conceptually:

```text
request source pages -> validate response envelope -> emit source records + metadata
```

Do not make downstream normalization depend on each provider's raw JSON structure.

Do not embed Airflow decorators/operators in reusable source clients.

## 2. Network Behavior

For every external source:

- use explicit connect/read timeouts
- respect documented rate limits and fair-use requirements
- use bounded retries for transient failures
- distinguish retryable failures from invalid data
- avoid unlimited pagination or infinite retry loops
- use HTTPS endpoints
- keep credentials in configured secret systems/environment, never source code

Do not scrape a site when a public API/feed is the selected source unless scraping is explicitly approved for that source.

## 3. Pagination

Implement pagination as part of the source adapter contract.

Test:

- first page
- multiple pages
- empty final page/cursor
- repeated cursor/page
- malformed pagination metadata
- maximum bounds when the source behaves unexpectedly

Avoid holding every page in memory if records can be processed incrementally.

## 4. Attribution and URLs

Preserve:

- provider/source name
- provider record ID
- original job/source URL
- application URL when distinct

A SkillSync user should ultimately be able to follow the original application destination.

Validate URL structure before exposing/storing it as trusted navigation data. Do not execute or fetch arbitrary user-controlled URLs from pipeline code.

## 5. Schema Drift

Treat third-party response shapes as unstable contracts.

When a source changes:

1. capture a minimal sanitized fixture reproducing the new response
2. add/update a contract/parser test
3. adjust the adapter
4. avoid weakening validation merely to make the test green

Unexpected mass nulls or rejection spikes should be visible as quality failures, not silently accepted.

## 6. Failure Handling

One malformed record should not necessarily kill an entire source run.

Classify failures:

- request/source outage -> retry/fail according to policy
- response envelope malformed -> fail source extraction
- individual record malformed -> quarantine/reject with reason
- optional field malformed -> null/warn when safe

Make the choice explicit.

## 7. Fixtures

CI fixtures should be:

- small
- representative
- sanitized
- stable
- free of secrets
- sufficient to reproduce known edge cases

Do not use live network calls as a substitute for fixtures in normal test suites.

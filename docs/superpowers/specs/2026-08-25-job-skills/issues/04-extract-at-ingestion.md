# 04 — Extract skills during ingestion

## Why
Job postings arrive through `job_ingestion`. Extracting their skills at arrival
is the only moment the full text is already in hand and nothing is waiting on
it.

## Prerequisites
#130 (the gate), #02 (the extractor), #03 (the tables).

## Scope
- The ingestion pipeline loads the current vocabulary, runs `platform_skills`
  over each posting's text, and writes the result: resolved mentions into
  `job_skills`, and every unresolved mention into `job_skill_mentions`.

  The gate decided in #130 is closed for matching and open for observation:
  nothing unresolved may ever reach `job_skills`, and nothing unresolved may be
  promoted to a concept, but the mention itself is recorded with its
  provenance. Recording an observation is not admitting a skill. Do not filter
  observations by frequency, shape, or any other rule — the whole point is that
  no such rule has been measured yet, and filtering now would destroy the
  evidence needed to measure one.
- Extraction happens inside the same transaction that persists the job. A job
  with half its skills is worse than a job with none, because the missing half
  is invisible.
- `occurrences` is the number of times the term appears in that posting's text,
  never the number of runs that observed it. Re-extraction recomputes it from
  the text and updates the row. An hourly re-run of an unchanged posting must
  leave the value identical — assert this in a test, because an incrementing
  counter would look plausible for weeks before anyone noticed the frequency
  evidence was worthless.
- Re-running ingestion over a posting already stored replaces its skills rather
  than appending. The second run of a source is a no-op today and must stay one.
- The run summary reports what extraction did: how many mentions resolved, how
  many were stored as unknowns, how many were discarded by the gate. A pipeline
  that silently drops most of its extractions should be visible in the summary,
  not discovered later.

## Do not change the lifecycle
Nothing here touches precedence, matching, retirement, or withdrawal. A run
that fails extraction still stores the job; skills are an enrichment, not a
validity condition.

## Out of scope
CV-side extraction, which belongs with the Phase C CV work and reuses the same
package. Embeddings (#131). Matching.

## Acceptance
- A run against the real Arbeitnow and Greenhouse boards stores skills. Report
  the run summary, the number of jobs, the number of `job_skills` rows, and the
  number of `job_skill_mentions` rows.
- Running the same source twice does not duplicate skills and does not grow the
  tables. Paste both counts.
- Spot-check ten postings by hand: quote the posting text and the concepts
  stored against it, and say whether they look right. A number that cannot be
  read back to the source text is not evidence.
- The service's tests pass with its coverage gate.

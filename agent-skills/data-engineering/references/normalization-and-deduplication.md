# Normalization and Deduplication

## Contents

1. Normalization principles
2. Text and HTML
3. Location and enums
4. Time
5. Deduplication order
6. Cross-source deduplication
7. Idempotency

## 1. Normalization Principles

Prefer small deterministic functions with explicit input/output contracts.

Keep source-display values when destructive normalization would remove information needed for UI, audit, or debugging.

Typical normalization includes:

- trimming/collapsing whitespace
- Unicode normalization where justified
- normalized comparison forms for company/title
- employment-type mapping
- remote-status mapping
- country-code mapping
- cleaned description text
- stable URL normalization where safe

Do not lowercase or strip punctuation from every user-facing field merely because a dedupe key needs it.

## 2. Text and HTML

External job descriptions are untrusted input.

- preserve raw HTML only when there is a concrete need
- sanitize HTML before any rendering path
- derive clean text for NLP/search/analytics
- do not execute scripts or embedded content
- do not log full descriptions by default

Normalization should be deterministic so the same source payload produces the same cleaned text under the same code version.

## 3. Location and Enums

Do not over-infer location.

If a source provides only `Europe`, do not manufacture a city/country.

Model remote semantics explicitly when possible, for example:

```text
remote
hybrid
onsite
unknown
```

Map employment types through a documented vocabulary and retain unknown/null when a safe mapping does not exist.

## 4. Time

- parse timestamps deliberately
- retain source timestamp when useful
- store normalized timestamps in UTC unless repository convention differs
- do not replace missing publication time with fetch time
- distinguish `published_at`, `source_updated_at`, `fetched_at`, `first_seen_at`, and `last_seen_at`

These timestamps answer different questions and should not be collapsed into one convenient column.

## 5. Deduplication Order

Prefer deterministic identity signals in this order:

1. same source + same external ID
2. canonical application/source URL when stable
3. deterministic fingerprint from selected normalized identity fields
4. cautious fuzzy similarity as supporting evidence

Possible fingerprint fields include normalized company, title, location, and a stable URL component. Inspect real source behavior before finalizing the key.

Never deduplicate solely by title.

## 6. Cross-Source Deduplication

The same employer job can appear in multiple feeds.

If cross-source records are merged into one canonical job:

- preserve all source identities/provenance
- preserve enough metadata to update each source independently
- avoid losing a valid application URL
- define conflict resolution for differing fields
- prefer authoritative source values when a hierarchy is explicitly known

Do not silently choose whichever record happened to arrive last.

## 7. Idempotency

For identical input and unchanged transformation rules, rerunning a pipeline should not create additional logical jobs or skill relationships.

Test idempotency explicitly:

```text
run(input) -> state A
run(input) -> state A (except run/audit metadata)
```

Use database constraints and upsert rules as a final guard, not only in-memory duplicate removal.

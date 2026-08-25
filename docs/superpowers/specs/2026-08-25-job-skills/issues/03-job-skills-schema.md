# 03 — `job_skills` and `job_skill_mentions`

## Why
Nothing links a job to a skill. `candidate_profile_skills` already points a
profile at a concept; this is the other half, and matching is the overlap
between them.

## Prerequisite
#130. The mentions table stores unknowns, and the rule deciding which unknowns
may be stored has to exist before the table that stores them.

## Scope
Two tables in `platform_db`, with a migration in the platform chain:

```sql
job_skills(
  job_id        uuid → jobs(id) on delete cascade,
  concept_id    uuid → skill_concepts(id) on delete restrict,
  alias_version varchar → skill_alias_versions(version),
  surface_form  varchar,
  primary key (job_id, concept_id)
)

job_skill_mentions(
  id                uuid primary key,
  job_id            uuid → jobs(id) on delete cascade,
  surface_form      varchar not null,   -- raw, exactly as the posting wrote it
  normalized_form   varchar,            -- nullable: normalization may not apply
  occurrences       integer not null,   -- times the term appears in THIS posting
  first_seen_at     timestamptz not null,
  last_seen_at      timestamptz not null,
  extractor_version varchar not null,
  alias_version     varchar not null → skill_alias_versions(version),
  evidence          jsonb,
  unique (job_id, surface_form, extractor_version, alias_version)
)
```

- `job_skills` is what matching and analytics read. The primary key is the pair,
  so one job cannot carry a concept twice.
- `alias_version` records which vocabulary resolved the mention, so extraction
  can be re-run under a new version and compared. Without it, "extracted under
  v1" and "absent from v2" are indistinguishable.
- `surface_form` is what the posting actually said. It is not decoration: the
  product shows matched skills, and "matched because the posting said Postgres"
  is a different experience from an unexplained checkmark.
- `job_skill_mentions` is an inbox for unresolved mentions. Nothing matches
  against it, nothing joins it to `skill_concepts`, and no API exposes it. It
  exists to make the gate decidable later: the evaluation in
  `gate-evaluation.md` failed for want of records linking a candidate to its
  posting, employer, and span, and this table accumulates exactly those from
  live ingestion.
- `alias_version` records the vocabulary under which resolution **failed**, and
  `extractor_version` the extractor that produced the mention. Both are needed:
  a term stops resolving either because the extractor changed or because the
  vocabulary did, and one version alone cannot distinguish them. Both are in the
  uniqueness key, so observations made under different vocabulary versions stay
  distinguishable rather than overwriting each other — which is what makes
  "this resolved under v2 but not v1" answerable.
- `occurrences` counts how many times the term appears **in that posting's
  text**. It is not a count of ingestion runs that saw the term. Two identical
  hourly re-runs of the same source must leave it unchanged: re-extraction
  recomputes the value from the text and updates the row, it never increments.
  Cross-posting frequency — the thing a future recurrence rule would be scored
  on — comes from counting distinct `job_id` values for a normalized form, not
  from this column.
- `first_seen_at` and `last_seen_at` bound when the observation was current.
  `last_seen_at` advances on re-extraction; `first_seen_at` does not. `normalized_form` is a column and is indexed, because the gate's
  question is a frequency question across postings; `evidence` is JSONB because
  spans, context, and extractor metadata have a shape that will change and are
  never aggregated.
- Cascade from `jobs` on both, so removing a job takes its skills with it.
  Restrict on `skill_concepts`, so a concept in use cannot be deleted out from
  under a job.

## Out of scope
Populating either table — that is #04. Matching. The API.

## Acceptance
- The migration lives in the platform chain, and both chains still autogenerate
  empty afterwards.
- Applying the platform chain then the backend chain to an empty database
  produces the new tables with the constraints above. Verify with `pg_dump`
  and paste the two table definitions.
- `alembic downgrade` removes them cleanly.
- Model tests cover the constraints that matter: the composite primary key, the
  cascade, and the restrict.

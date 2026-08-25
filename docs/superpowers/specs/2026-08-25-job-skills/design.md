# Job skills — storage and extraction design

Date: 2026-08-25

## What is being decided

Nothing currently links a job to a skill. `skill_concepts`,
`skill_surface_forms`, and `skill_alias_versions` exist and hold the
vocabulary; `candidate_profile_skills` points a profile at a concept. The job
side of that relationship is missing, and so is the extractor that would
populate it.

## The shape

Two tables, because resolved and unresolved skills are different things with
different readers.

```sql
job_skills(
  job_id        uuid → jobs(id) on delete cascade,
  concept_id    uuid → skill_concepts(id) on delete restrict,
  alias_version varchar → skill_alias_versions(version),
  surface_form  varchar,
  primary key (job_id, concept_id)
)

job_skill_mentions(
  id              uuid primary key,
  job_id          uuid → jobs(id) on delete cascade,
  normalized_form varchar,   -- indexed
  surface_form    varchar,
  evidence        jsonb
)
```

`job_skills` is what matching and analytics read. `job_skill_mentions` is an
inbox: nothing matches against it, and a mention only becomes a concept by
passing the gate.

### Why not one JSON column of skills per job

It was considered and rejected. The vocabulary already solves the problem a
JSON column would be reaching for: `skill_surface_forms` maps every spelling of
a skill onto one concept, versioned by `skill_alias_versions`. Storing skill
strings per job re-admits the 36.7% annotator disagreement measured in Phase B
as distinct values.

Concretely, against requirements that already exist:

| Requirement | Relational | JSON column |
| --- | --- | --- |
| Most requested skills (§12) | `GROUP BY concept_id` | unnest and group by text; spellings count separately |
| Common skill combinations (§12) | self-join | array intersection in application code |
| CV-to-job matching | UUID set overlap, indexed | string comparison, no integrity |
| Correcting the vocabulary | one row | rewrite every stored posting |

The last row decides it. When `k8s` turns out to belong to Kubernetes,
relational is one insert; JSON is a migration across every posting ever stored,
and 985 already persist.

### Why JSON is still right for `evidence`

Span offsets, surrounding context, extractor version, and confidence have a
shape that will change and are never aggregated across rows. That is what JSONB
is for. `normalized_form` stays a column because the gate's question is a
frequency question across postings, which JSON cannot answer honestly.

### Why `alias_version` is on `job_skills`

So extraction can be re-run under a new vocabulary and compared against the
old. Without it, "extracted under v1" and "absent from v2" are
indistinguishable.

## Where the extractor lives

Extraction runs on both sides: job text during ingestion, CV text on upload.
Same behaviour, two callers.

It cannot live in `platform_db` — the CI contract from #167 allowlists that
package to models, migrations, and the session factory, deliberately, to stop
it becoming the data-access service that was rejected.

So: a fourth package, `platform/skills`. A pure function of
`(text, vocabulary) → mentions`, with no I/O and no database access, depended
on by `job_ingestion` and by the backend. Behaviour is identical on both sides,
so this is a shared library, not a service — the same rule that put the schema
in a package rather than behind an API.

## Sequence

| # | Work | Nature |
| --- | --- | --- |
| 1 | The unknown-skill gate — decided by measurement | decision |
| 2 | `platform/skills` extractor package | code |
| 3 | `job_skills` and `job_skill_mentions` schema | migration |
| 4 | Extraction at ingestion populates both | code |

Job embeddings (#131) and the matching baseline follow, and are not in this
spec.

The gate comes first because it decides what may be stored. The skill model
decision says so directly: preserving unknowns re-admits the 85% junk that got
free text rejected unless something decides which unknowns are real.

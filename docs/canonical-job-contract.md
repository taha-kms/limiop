# Canonical Job Contract

SkillSync stores one source-independent representation of a job. Every provider
maps onto this contract, and nothing downstream — the API, analytics, matching —
needs to know which provider a job came from.

This is now an interface between two deployables rather than an internal
backend convention. `services/job-ingestion-service` produces and persists the
canonical job, while `backend` reads and serves it. A change therefore costs a
coordinated service, database, and API change and should be treated as a
coordinated interface change rather than a local refactor.

The contract is represented in three existing modules:

- `services/job-ingestion-service/job_ingestion/schemas.py` validates the
  normalized input accepted by ingestion persistence.
- `platform/db/platform_db/models/catalog.py` holds the PostgreSQL tables and
  vocabulary, which are the schema authority.
- `backend/app/modules/jobs/schemas.py` holds the validated API read contract.

## Vocabulary

Three closed vocabularies classify every stored job. Provider values that do not
map onto a member become `unspecified` rather than being dropped or invented.
`status` has no `unspecified` member because lifecycle is decided by SkillSync,
not by the provider.

| Vocabulary | Members |
| --- | --- |
| Workplace type | `remote`, `hybrid`, `onsite`, `unspecified` |
| Employment type | `full-time`, `part-time`, `contract`, `internship`, `temporary`, `unspecified` |
| Status | `active`, `expired`, `removed` |

## Input: `NormalizedJob`

`NormalizedJob` is the only shape a provider normalizer may produce, and the only
shape persistence accepts. It is immutable and rejects unknown fields, so a
provider cannot smuggle source-specific data into the canonical model.

| Field | Required | Notes |
| --- | --- | --- |
| `company.display_name` | yes | Trimmed, 1–255 characters. Normalized for lookup on write |
| `company.website_url` | no | Absolute HTTP(S) URL, at most 2048 characters |
| `title` | yes | Trimmed, 1–255 characters |
| `description` | yes | Plain text. HTML is stripped by the normalizer, never stored raw |
| `location` | no | Trimmed, 1–255 characters. Absent means unknown, not remote |
| `workplace_type` | no | Defaults to `unspecified` |
| `employment_type` | no | Defaults to `unspecified` |
| `application_url` | yes | Absolute HTTP(S) URL where the user applies |
| `published_at` | no | Timezone-aware. Absent means the provider did not say |
| `expires_at` | no | Timezone-aware. Must not precede `published_at` |
| `provenance` | yes | Nested, see below |

Optional means "the provider did not supply this", never "SkillSync chose not to
map it". A normalizer that cannot find a required field must fail the record
rather than substitute a placeholder.

### Nested provenance

Provenance is nested inside the job rather than passed alongside it, so a job
cannot be normalized without recording where it came from.

| Field | Required | Notes |
| --- | --- | --- |
| `source_key` | yes | Stable key of a registered `JobSource`, at most 100 characters |
| `source_job_id` | yes | The provider's own identifier for the record |
| `source_url` | yes | Where the record was read from |
| `raw_payload` | no | Untrusted provider JSON, preserved for reproducing transformations |
| `partial_description` | no | `true` when `description` is the provider's excerpt rather than the posting. Defaults to `false`. Stored inside `raw_payload` as `_partial_description`, always written, `true` or `false` |

Persistence folds two keys of its own into the stored `raw_payload`, prefixed
so they can never collide with a field the provider sent:

| Key | Meaning |
| --- | --- |
| `_partial_description` | `true` when the record's description was an excerpt, `false` otherwise. Written on every run, so a source that truncated once and recovered stops reading as a snippet. Deduplication never text-matches a row where it is `true` |
| `_stated_fields` | How many of the optional canonical fields (location, workplace type, employment type, published and expiry dates) the record itself stated. Ownership judges a rival against this, not against the merged job |

`(source_key, source_job_id)` identifies an external record. One canonical job
may carry provenance from several sources when the same posting is advertised in
more than one place.

## Output: `JobRead`, `CompanyRead`, `ProvenanceRead`

Read schemas are built from persisted rows and carry the database-assigned `id`,
`status`, and audit timestamps that inputs do not.

`ProvenanceRead` has no `raw_payload` field. Raw provider data is untrusted and
is never served, so the field is absent from the schema rather than excluded at
each call site.

## Validation rules

- URLs must be absolute HTTP(S) and fit the 2048-character column.
- Timestamps must be timezone-aware. Naive values are rejected, not assumed UTC.
- Text fields are trimmed, and whitespace-only values are rejected.
- Length limits mirror the PostgreSQL columns, so a value that validates can
  always be stored.
- `expires_at` may equal `published_at` but never precede it. The same rule is
  enforced again by a database check constraint.

## Rules this contract exists to enforce

- Source-specific fields stay out of the canonical job. If a value only makes
  sense for one provider, it belongs in `raw_payload`.
- Raw external data lives only in provenance.
- External job data is always untrusted: validated at the boundary, never
  rendered as HTML, never logged, never used to drive control flow.
- PostgreSQL and Alembic remain the schema authority. These schemas mirror the
  columns; they do not define them.


## When two sources describe the same job

A job may carry provenance from several sources, and they will not agree. The
same posting reads `London` on an aggregator and `London, UK` on the employer's
own board, and `unspecified` against `On-Site`. Neither is wrong; they are
differently precise.

Each source carries a **precedence**, stored on its row rather than held in
code, so the ordering that produced a stored record can be read back out of the
database. Higher wins.

Ownership is judged among a job's **live rivals**: the other sources whose
provenance row is not retired. A source that stopped listing the posting no
longer ranks, so a board whose posting is gone from the board yields the text
to an aggregator that still carries it, and takes it back when the posting
reappears. One exception looks at retired rows too: a snippet never replaces a
full description another source supplied, even one that has since gone,
because the text the job holds is still that source's full text and an excerpt
is a worse account of the same posting. A source alone on a job may still
correct itself.

Four rules then decide a field:

1. **Silence never wins.** A source that says nothing about a field cannot erase
   what another source said. Nothing distinguishes a provider that dropped a
   field from one that never carried it, and most postings state no workplace
   arrangement at all, so the alternative is a catalogue that empties itself.
   A field is silent when it is null, or when it holds the `unspecified` member
   its vocabulary uses for exactly this.
2. **When both speak, rank decides.**
3. **At equal rank, the more complete record owns the job.** Aggregators copy
   the same employer text as each other, so rank cannot separate them and how
   much of the posting a record accounts for is the only signal left. A full
   description outranks a partial one; after that, the record stating more of
   the optional canonical fields (location, workplace type, employment type,
   published and expiry dates) wins. The comparison is between the two
   sources' own records, read from the `_partial_description` and
   `_stated_fields` keys their provenance rows carry (see the provenance
   section), never against the merged job: the job holds what every
   contributor said, so measured against it no single source could stay
   complete enough to change the text again.
4. **At equal completeness, the source that listed the job first keeps it.**
   Once both sources have been seen, that date is the same whichever of them
   ran last, so the record stops depending on the order of the runs. A source
   with no live rival at its rank, or one that listed the job before its
   rivals, still lands its own corrections.

A lower-ranked source that wins nothing still records that it saw the job, and
still refreshes when it last did. Losing a disagreement is not the same as being
ignored, and the lifecycle rule depends on knowing who saw what and when.

The stored match key is recomputed from the merged result rather than from the
record that arrived. A job several sources contributed to holds values no single
record carries, and a fingerprint describing the incoming record would describe
a job that is not stored.

Ownership only applies once two records are recognised as the same job, which
is what the next section decides.

### Alternatives considered

**First creator owns.** Whichever source saw a job first would keep it forever.
Rejected as the rule because arrival order is an accident of scheduling, and it
would freeze an aggregator's thinner account of a posting in place ahead of the
employer's. It survives only as the last tie-break, once rank and completeness
have both failed to separate two sources, where the alternative is a record
that follows whichever run happened last.

**Precedence per field.** A source could outrank another on location while
losing on description. Rejected as unjustified for now: it needs per-field
ownership recorded somewhere, and no observed disagreement calls for it. The
silence rule already delivers most of the benefit, since a source only loses
fields it actually contests.


## When two records are the same posting

Identity is a two-stage test, and neither stage is enough on its own.

**The match key blocks candidates.** It hashes the employer and the normalized
title, and it deliberately answers only "might these be the same posting".

**The place and the text decide among them.** Two records are the same posting
when they name the same cities and read the same way.

### Why the location is compared rather than hashed

Twenty-nine cross-source duplicates were confirmed by their descriptions and
then examined. **Every one of them described its location differently**:
`London` against `London, UK`, `Berlin, Berlin` against
`Berlin, Berlin, Germany`. An aggregator drops the country that the employer's
own board keeps. A key containing the location matched none of them, so the
catalogue stored each of those jobs twice.

Removing the location entirely is worse. Replaying ten thousand real postings
that way collapsed two thousand distinct openings into each other, because one
employer runs the same role in Seoul, Tokyo, Sydney and Mumbai and those are
four jobs, not one.

So the cities are extracted and compared. A side that names no city matches
anything, because it has made no claim to contradict, which covers the common
case of one source saying only `Remote`.

### Why the descriptions are compared too

Comparing cities still merged distinct requisitions that share one: two Staff
Engineer openings in Dublin with different text. Nothing in the employer, the
title, or the place separates them.

Requiring the descriptions to share at least 85% of their vocabulary removed
every measured wrong merge. Confirmed duplicates share no less than 96.6%, and
measured wrong merges reached 82%, so the threshold sits in a wide gap rather
than on a boundary: recall was unchanged anywhere from 0% to 95%.

**This assumes a source carries the employer's own words.** Both current sources
do. A source that wrote its own summaries would fail this check on every record,
and its duplicates would be missed silently. That makes it an assumption about
how a source obtains its text, not a constant.

A source that delivers a snippet rather than the posting cannot make that
assumption hold, and says so: its records are stored with
`partial_description`, and the text check is never consulted for them, from
either side. A snippet arriving beside a stored full-text posting of the same
role and place is stored as a second job, and a full-text posting arriving
beside a stored snippet is too. The record is therefore allowed to duplicate
another source's posting rather than risk merging two different jobs on the
strength of a shared opening sentence, for the same reason the subset rule
below was rejected: a missed duplicate shows a job twice and is visible, while
a wrong merge deletes a job silently. Provenance still recognises the same
snippet record when its own source sends it again.

### Measured

Against a real corpus of 400 aggregator postings and 10,279 employer-board
postings, with duplicates labelled independently by description similarity:

| | cross-source duplicates found | wrong merges |
| --- | --- | --- |
| Location hashed into the key | 0 of 29 | 0 |
| Location dropped entirely | 26 of 29 | 2,135 collapsed |
| Cities compared, no text check | 24 of 29 | 12 |
| **Cities compared, text compared** | **24 of 29** | **0** |

Allowing one city set to be a subset of the other found three more duplicates
and cost one wrong merge. It was rejected: a missed duplicate shows a job twice
and is visible, while a wrong merge deletes a job silently.

### The five it still misses

All the same shape: one source names a single city while the other lists many,
so the sets differ without disagreeing. `Freiburg` against a list of eleven
offices including Freiburg. These are stored twice.


## When a job stops being open

Postings disappear from a board rather than announcing that they closed. Every
source examined carries an expiry field in its schema and leaves it empty in
practice, so absence between runs is the only signal there is.

### Absence is only evidence when nothing else explains it

A run reports two different things, and conflating them was the hazard:

- **processing complete** — every record this run fetched reached an outcome.
- **source exhausted** — this run saw everything the source has.

Only the second licenses concluding that an unseen posting is gone. A run that
stopped at its record budget, gave up on a board, or failed on a single record
has postings it never looked at, and an unseen posting is indistinguishable
from one that is gone.

The two come apart constantly. A run capped at five records against a board of
twenty-nine is processing-complete and not exhausted; treating it as licence
would have withdrawn twenty-four open jobs.

Reconciliation refuses to run at all without exhaustion, and says why rather
than doing nothing quietly.

One run is refused even when its counts call it exhausted. A run that fetched
no records reads the same whether the source was empty or never answered, and
retiring every posting on the strength of it would let an outage do the
retiring. Such a run retires nothing and reports that it saw no records and
cannot tell absence from an outage.

### A creation-windowed source keeps a posting for a presumed lifetime

A source that is read through a window can never claim exhaustion. Adzuna is
asked only for postings created in the last two days, so a walk that runs
every country short has still seen nothing older than the window, and its
client reports `reached_the_end` as false on every run. Nor does absence from
such a source mean anything: a posting leaves the window two days after it was
created whether or not it is still open, and the API has no closing signal.

Such a source states a presumed lifetime instead: how long a posting is kept
after the source last showed it before SkillSync retires it, carried on the
run summary as `retire_unseen_after`. This is a lifetime, not evidence of
absence. Adzuna states thirty days, so an Adzuna posting is shown for thirty
days after it was last seen, roughly thirty to thirty-two days after it was
created, whether or not Adzuna still lists it: the API never says when a
posting closes, the terms permit holding the data while the licence stands,
and a posting older than that is more often filled than open.

A run stating a lifetime retires the provenance records of its source last
seen before the run started minus the lifetime, and withdraws jobs exactly as
an exhausted run does, provided it fetched at least one record, did not stop
at its record budget, and can account for every record it fetched. The rule's
inputs are the moment the run started and the stated lifetime; nothing in the
run's counts moves the line. Record failures do not refuse this path, unlike
the exhaustion path: the lifetime runs from when the source last showed the
posting, and a record this run failed to read says nothing about that.

A run that stopped at its record budget is refused, a run whose records
vanished without a failure is refused, and a run that saw no records is
refused before either rule is consulted. The exhaustion rule is unchanged: a
run that reached the end retires everything it did not see, whatever lifetime
it states.

### The conclusion is drawn twice

**Per source.** A provenance record an exhausted run did not see, or one a
windowed source has not shown for its stated lifetime, is retired. That is a
fact about one board: this employer stopped advertising this posting there,
or the lifetime SkillSync keeps it for has run out.

**Per job.** A job is marked `removed` only once no source still lists it. A
job dropped by an aggregator but still on the employer's own board is still
open, and saying otherwise would hide a real vacancy.

Seeing a posting again reverses both steps, so a posting that returns is the
job it was rather than a new one.

### Expiry is not removal

A job past a date it stated itself becomes `expired`. That is a stated fact
rather than an inference from absence, so it needs no exhausted run and no
provenance. A job that stated no date never expires on its own, which is every
job the catalogue currently holds.

### Nothing that stopped being listable is kept as it was

A job that is no longer `active` is not served, but until retention runs it is
still stored in full, raw payloads included. Two licences forbid keeping that
indefinitely, so the `catalogue_retention` DAG runs a pass nightly at 03:15
with one rule and a **grace period** of 30 days, counted from when the job last
changed. A status flip moves `updated_at`, so the grace starts the moment
reconciliation or expiry acted; a source that keeps writing the job restarts
it, because a job still being sent has not left any listing.

Once the grace has run out, one of two things happens:

- **Deleted.** A job nothing user-facing references leaves with its provenance,
  skills and mentions, in one transaction.
- **Anonymised.** A job that user-facing rows still point at keeps its row so
  the history keeps its shape, but every provenance `raw_payload` becomes
  `{"_anonymised_at": "<when>"}`, the description becomes
  `Posting no longer available`, and the location and application URL are
  cleared. The company link and the status stay, the first because the schema
  requires one, the second because an anonymised job is still the withdrawn or
  expired job it was.

`_anonymised_at` is the marker: a job carrying it is never a candidate again,
so the pass is idempotent. Which rows count as user-facing references is a
policy the retention module is given, not something it knows; nothing in the
schema qualifies yet.

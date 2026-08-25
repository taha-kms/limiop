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

Three rules decide a field:

1. **Silence never wins.** A source that says nothing about a field cannot erase
   what another source said. Nothing distinguishes a provider that dropped a
   field from one that never carried it, and most postings state no workplace
   arrangement at all, so the alternative is a catalogue that empties itself.
   A field is silent when it is null, or when it holds the `unspecified` member
   its vocabulary uses for exactly this.
2. **When both speak, rank decides.**
3. **An equal rank goes to the incoming record**, so one source can still
   correct itself.

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
Rejected because arrival order is an accident of scheduling, and it would freeze
an aggregator's thinner account of a posting in place ahead of the employer's.

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

### The conclusion is drawn twice

**Per source.** A provenance record an exhausted run did not see is retired.
That is a fact about one board: this employer stopped advertising this posting
there.

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

# Canonical Job Contract

SkillSync stores one source-independent representation of a job. Every provider
maps onto this contract, and nothing downstream — the API, analytics, matching —
needs to know which provider a job came from.

The contract lives in `backend/app/modules/jobs/`:

- `domain.py` holds the vocabulary and normalization rules.
- `models.py` holds the PostgreSQL tables, which are the schema authority.
- `schemas.py` holds the validated Python contract described here.

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

The stored fingerprint is recomputed from the merged result rather than from the
record that arrived. A job several sources contributed to holds values no single
record carries, and a fingerprint describing the incoming record would describe
a job that is not stored.

### What this does not cover

Ownership only applies once two records are recognised as the same job, and
recognition runs on company, title, and location. Two sources that describe the
location differently never reach this rule: they produce different fingerprints
and two stored jobs. That is deduplication rather than ownership, and it is
tracked separately.

### Alternatives considered

**First creator owns.** Whichever source saw a job first would keep it forever.
Rejected because arrival order is an accident of scheduling, and it would freeze
an aggregator's thinner account of a posting in place ahead of the employer's.

**Precedence per field.** A source could outrank another on location while
losing on description. Rejected as unjustified for now: it needs per-field
ownership recorded somewhere, and no observed disagreement calls for it. The
silence rule already delivers most of the benefit, since a source only loses
fields it actually contests.

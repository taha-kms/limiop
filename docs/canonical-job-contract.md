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

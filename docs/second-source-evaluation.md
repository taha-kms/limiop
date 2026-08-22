# Choosing the second job source

Phase A.5 adds a second provider in order to resolve three gaps that are
currently theoretical: which source owns a canonical field (#93), when a job
becomes expired or removed (#94), and whether the fingerprint survives crossing
a source boundary (#95).

That purpose decides the choice. A provider whose postings never coincide with
Arbeitnow's would grow the catalogue and leave all three gaps exactly as
untested as they are now.

Everything below was measured against the live APIs in August 2026, not taken
from documentation.

## The tension

The two things a second source can be good for pull against each other.

**New supply** wants a provider that lists jobs Arbeitnow does not have.
**Overlap** wants a provider that lists the same jobs Arbeitnow does, so the
catalogue has to reconcile them.

Measured overlap with one page of Arbeitnow (175 jobs, 99 companies):

| Candidate | Companies sampled | Also on Arbeitnow |
| --- | --- | --- |
| Jobicy | 61 | 2 |
| Remotive | 13 | 0 |
| Himalayas | 18 | 0 |
| Greenhouse boards | 30 | 18 reachable, and every shared posting matched |

The remote-first boards are a different market. They are mostly United States
and global-remote, while Arbeitnow is Germany-first, so they barely intersect.

## Candidates

| | Access | Cost | Coverage | Overlap | Licence | Canonical fit |
| --- | --- | --- | --- | --- | --- | --- |
| **Greenhouse boards** | Keyless | Free | Per company, worldwide | **Total, for shared companies** | Public by design | Good; needs employment type from metadata |
| Ashby boards | Keyless | Free | Per company | High, same shape | Public by design | Good |
| Lever boards | Keyless | Free | Per company | High, same shape | Public by design | Good |
| Jobicy | Keyless | Free | Global remote | Near zero | Public feed | Good |
| Remotive | Keyless | Free | Global remote | Zero measured | Public feed | Good |
| Himalayas | Keyless | Free | Global remote | Zero measured | Public feed | Good, and carries an expiry date |
| The Muse | Keyless | Free tier | Mostly United States | Not measured, likely low | Attribution terms | Fair; nested company and location |
| Adzuna | **App key** | Free tier, then negotiated | Twenty markets including Germany | Likely high | **Fourteen-day trial for organisations, written consent beyond it** | Good |

Adzuna is the strongest alternative on paper: it covers Germany, so it would
overlap. Its terms make it unsuitable here. Continued use by an organisation
needs written consent after a fourteen-day evaluation, and it needs credentials,
which would introduce the first secret this project has to manage.

## Recommendation: company job boards, starting with Greenhouse

Arbeitnow is an aggregator. The companies it lists publish the same openings on
their own applicant tracking systems, and those systems answer without
credentials. Eighteen of thirty sampled Arbeitnow companies were reachable that
way on a first guess at their board name.

### It does not trade supply for overlap

The obvious objection is that the same companies mean the same jobs. Measured,
the opposite is true:

| Company | On Arbeitnow | On its own board |
| --- | --- | --- |
| Anthropic | 3 | 476 |
| Datadog | 1 | 359 |
| Hudl | 1 | 29 |

Aggregators carry a sample. The board carries everything. So this choice grows
the catalogue by two orders of magnitude for the companies it covers, while
still guaranteeing the overlap the three gaps need.

### The case against it

Boards are per company, so the source is a list of boards rather than one
endpoint, and nothing discovers that list. Eighteen of thirty came from guessing
a slug from the company name; the other twelve may use a fourth system, a
different slug, or no public board. **Board discovery is unsolved**, and
maintaining the list is the real cost of this option.

Three platforms cover the sample, which means three clients rather than one.
They are small — Ashby and Lever return a similar shape — but it is three.

Rate limits are undocumented. The board API is heavily cached and has no
published hard limit, and reasonable polling is fine, but hammering many boards
would get throttled. Polling a bounded list a few times a day is the intended
usage.

## What the source makes possible

### #93, which source owns a canonical field

The same posting, read from both sources on the same day:

| | Arbeitnow | Greenhouse |
| --- | --- | --- |
| location | `London` | `London, UK` |
| workplace | `remote: false`, so `unspecified` | metadata `Location Type: On-Site` |

Neither is wrong. They are differently precise, and today the last writer wins,
so the stored value depends on which run finished most recently.

This also makes `onsite` reachable for the first time. Nothing has ever been
stored as onsite, because Arbeitnow only ever flags remote, and #108 refused to
infer onsite from silence. Greenhouse states it outright.

### #94, when a job becomes expired or removed

`application_deadline` is present in the schema and empty in practice: zero of
476 Anthropic postings and zero of 29 Hudl postings carry one. A lifecycle rule
cannot key on a stated expiry date.

The usable signal is absence: a posting that was on the board yesterday and is
not there today. That is a set difference against what the previous run saw, and
**the pipeline cannot express it**. `IngestionRun.execute` walks the records it
fetched and writes each one; nothing compares that against prior provenance.
`JobStatus.EXPIRED` and `JobStatus.REMOVED` exist in the vocabulary and are
assigned nowhere in the application.

So #94 is an ingestion change rather than a rule to write down, and it is the
most expensive item in the phase.

It also carries a hazard worth stating before anyone builds it. Runs are bounded
by `max_records`, currently five hundred in the DAG, and a fetch can fail
halfway. Reconciling a truncated run against the catalogue would expire every
job the run did not reach. Absence may only be concluded from a run that
completed, which is what `IngestionSummary.is_complete` already reports.

### #95, whether the fingerprint survives a source boundary

It does not, and this can be shown rather than argued. Feeding the two readings
of that one Anthropic posting through the project's own `fingerprint()`:

```
arbeitnow  v1:aadc382ed5a0cef8a551c0416d9038eeaf4711ad94dd910485fec8fff465ac9f
greenhouse v1:3fc62e1db00fb30014c83ea2fad482281c6ea094a6e7a3368ef5140c8660386b
```

Location is a fingerprint input, `London` and `London, UK` normalize
differently, and the catalogue would therefore store one job twice.

That points at an order. The fingerprint diverges *because* the sources disagree
about a field, so #93 comes first: settle precedence, then measure how much of
the dedup gap is left. Fixing #95 first would be tuning a hash around a
disagreement nobody had resolved.

## One thing the second source already validates

Greenhouse returns its description as entity-escaped HTML, the same shape that
caused #104 on Arbeitnow. The fix made there flattens until the result stops
changing, so it handles this without alteration. The normalizer contract does
not need to move to accept a second provider.

## Open: where a persistent environment lives

Unchanged and deliberately unresolved, but the phase makes the consequence
concrete. A lifecycle rule based on absence between runs can only be validated
by runs that persist between them. Throwaway databases can prove a fetch works;
they cannot prove that a job which vanished yesterday is expired today.

That does not block designing the rule or writing its tests, which can seed two
states directly. It blocks observing it against the real board.

## Sources

- Greenhouse Job Board API is public and unauthenticated, with no published hard
  rate limit: <https://developers.greenhouse.io/job-board.html>
- Adzuna terms of service, including the fourteen-day organisational trial:
  <https://developer.adzuna.com/docs/terms_of_service>

# Keyed sources — design

Date: 2026-09-15.

## Problem

Every source so far passed one filter: a documented public feed that needs no
key. That filter is why the catalogue is what it is. The feeds that exist
without a key are published by the remote-work and technology niche, so the
catalogue is remote-heavy and technology-leaning by accident, not by decision.
Retail, healthcare, trades, public administration, and on-site office work
mostly live behind national employment services and licensed aggregators,
none of which is keyless.

The product is for job seekers with no stated geography or sector. Reaching
them means accepting keyed and licensed sources. Two things follow: the
project must handle its first third-party secrets, and the source policy must
say what an acceptable licence looks like.

## Decision

- **Market is global and all sectors.** The catalogue's present skew is
  recorded as a consequence of sourcing, and the goal is to remove it. No
  country is first; the order in which national services are added follows
  the cleanest licence, not a home market.
- **Keyed sources are admitted.** A source may need a key, an account, or a
  signed agreement. The gate gains a fifth question: is the key obtainable by
  SkillSync on published terms, and what does it cost.
- **One secrets rule, applied everywhere.** A secret is read from the
  environment at process start, is never written to a log, a run summary, a
  fixture, the registry, or a payload, and is absent from every image, compose
  file, and repository file. The deployment baseline already states this for
  the two existing secrets; keyed sources reuse it rather than invent one.
- **Sources declare what they need.** A source that needs credentials names
  the environment variables it reads. A run with the variable unset is not an
  error at import time: the source reports itself as unconfigured and the
  scheduler skips it, so a deployment can enable sources one at a time.
- **Quotas are enforced by the client, not hoped for.** A licensed source
  publishes a daily or monthly call budget; the adapter stores calls made per
  UTC day on the run record and refuses to exceed the budget, so a
  misconfigured schedule cannot burn an account.

Rejected: a vault or secret-manager integration now (the deployment target is
undecided; environment injection is what every target supports), and storing
keys in `SKILLSYNC_SOURCE_CONFIG` (it is a JSON blob that gets logged in
diagnostics; one variable per secret keeps the logger's field-based redaction
simple).

## Credentials

```python
@dataclass(frozen=True, slots=True)
class Credential:
    env: str            # e.g. "SKILLSYNC_ADZUNA_APP_KEY"
    secret: bool = True # False for an app id that is not confidential

class SourceCredentials(Protocol):
    required: tuple[Credential, ...]
```

`job_ingestion/credentials.py` reads them: `resolve(required) -> Mapping[str, str] | Unconfigured`.
`Unconfigured` names the missing variables without their values. Every keyed
`ingest_*` entry point calls it first and returns an `IngestionSummary` with
`fetched=0` and one `RecordFailure(stage=FETCH, reason="source unconfigured: SKILLSYNC_ADZUNA_APP_KEY")`
rather than raising, so the run is recorded and visible. The DAG for a keyed
source checks the same thing and logs at warning level; it still runs, so the
run history shows the source is configured out.

Logging: the ingestion logger already writes structured fields. Every client
that carries a credential sends it in a header or a query parameter that the
logger never sees, because the client logs the URL path and status only, never
the full URL or headers. A test per keyed client asserts the secret string is
absent from every log record the client emits.

## Quotas

`job_ingestion/quota.py`: `async def reserve(session, source_key, *, calls, per_day) -> bool`
counts calls made today for the source on a new `source_quota_usage` row
(`source_key`, `day`, `calls`) in `platform/db` and refuses when the budget
would be exceeded. Clients call it before each request. A refused reservation
ends the run with `stopped_at_budget=True` and no failure, which the summary
already knows how to report. Per-minute limits stay with the existing 429
handling.

## Sources, in order

### Adzuna

Endpoint `https://api.adzuna.com/v1/api/jobs/{country}/search/{page}` with
`app_id`, `app_key`, `results_per_page` (max 50), `max_days_old`, `sort_by=date`.
Twenty countries. Terms (checked 2026-09-15): organisations may use the API
"subject to a 14 day trial period"; after it "a licence agreement may be
required"; every displayed advert must carry "Jobs by Adzuna" with the word
linked and the logo shown; quota "25 hits per minute, 250 hits per day, 1000
hits per week, 2500 hits per month".

Consequences the adapter must state:

- The monthly ceiling is the binding limit: 2,500 calls over a 31-day month
  is 80 a day, tighter than the weekly 1,000 (142 a day) and the daily 250.
  The daily ledger only counts days, so it enforces 80 calls a day, which is
  at most 4,000 postings a day across all countries. The adapter takes a
  configured country list and a per-country page budget and stops at the
  quota.
- `description` is a snippet, not the posting. The canonical contract requires
  a plain-text description and the deduplicator compares descriptions across
  sources. An Adzuna record is stored with its snippet, marked in provenance
  as `partial_description=true`, and the deduplicator treats a partial
  description as never matching by text. Skill extraction runs on what there
  is. This is a documented degradation, chosen over fetching every
  `redirect_url`, which the terms do not license.
- Attribution is a frontend obligation. The listing must render the "Jobs by
  Adzuna" label with logo and link on every Adzuna-sourced job. The adapter
  cannot satisfy it; the frontend issue is part of the delivery and the
  source stays disabled in production until it is merged.
- The organisation trial is fourteen days. The source is enabled in
  production only after the licence conversation with Adzuna has an answer;
  the policy row records the date the trial started.

### France Travail

Official API with a free account and OAuth2 client credentials. Licence
requires naming France Travail as source with the date of last update and a
link, and forbids sub-licensing the database. Full description inline.
Covers all sectors in France. Second, because the licence is explicit and
free; its onboarding needs a token flow, which is the second credential shape
the framework must support (client id + secret exchanged for a bearer token,
cached until expiry).

### UK Find a job (DWP)

Government job board with published feeds under the Open Government Licence,
which permits reuse with attribution. All sectors, UK. Third; confirm the
current feed shape in its own gate review, the site was unreachable on the
check date.

### National services with no official terms

Bundesagentur für Arbeit and EURES work today through client identifiers
taken from their own applications. They have no published terms for third
parties. They are recorded as blocked pending a written answer from the
operator, and an email is sent asking for sanctioned access. If either
answers yes, it joins the order above; the technical shape is already known.

## Policy

`docs/job-source-policy.md` gains:

- Gate question five: *Obtainable credentials* — can SkillSync obtain the
  required key or agreement on published terms, at what cost, and does the
  agreement permit storage and display with attribution.
- A "Tier two — licensed and keyed sources" section with the same table
  shape plus a column for the credential and the quota.
- The "terms silent" rule is unchanged: a documented feed whose terms say
  nothing is still blocked. Option two admits keys and licences; it does not
  lower the evidence bar.

## Delivery

| Issue | Change |
| --- | --- |
| 1 | Credentials: `Credential`, `resolve`, unconfigured runs, log-redaction test harness, deployment doc |
| 2 | Quotas: `source_quota_usage` table, `reserve`, summary reporting |
| 3 | Adzuna adapter: countries, page budget, snippet handling, provenance flag, dedup rule |
| 4 | Frontend: source attribution on the listing, "Jobs by Adzuna" rendering |
| 5 | Policy: gate question five, tier two, Adzuna row with trial date, BA and EURES blocked-pending entries |
| 6 | France Travail adapter with the OAuth2 credential shape |
| 7 | UK Find a job gate review and adapter |

1 and 2 first, in parallel. 3 and 4 next, together; the source ships disabled
until 4 lands. 5 with 3. 6 and 7 follow.

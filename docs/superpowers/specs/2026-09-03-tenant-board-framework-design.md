# Tenant-board ingestion framework — design

Date: 2026-09-03

## Problem

Greenhouse is a tenant-board source: one company slug, one request, every
posting that company has. Eight more systems on the candidate list in
`docs/job-source-policy.md` have the same shape — Lever, Ashby,
SmartRecruiters, Workable, Recruitee, Personio, Pinpoint, and Polymer. Today the
Greenhouse package owns its own transport, retry, board loop, slug discovery,
pipeline wiring, and DAG. Copying that eight times leaves eight places to fix
one bug, and drift between them is the likely outcome.

Two more candidates were checked and do not pass the policy gate:

- **JazzHR.** The XML feed URL is obtained inside the product per account and
  the official material describes it as scoped to that account's key. The
  documentation could not be retrieved. There is no documented public access
  path to build against.
- **Talexio.** No public developer documentation exists. An endpoint can be
  observed on a live careers site, but an observed endpoint is not a documented
  one, and one careers site can host several employers, so the slug does not
  even name the company.

Both go into the policy document as blocked, with the date checked.

## Decision

One generic client, one generic pipeline, one discovery module, one DAG
factory. A provider contributes a value describing what is specific to it and
nothing else.

- **Composition over inheritance.** The codebase describes stage boundaries as
  protocols and carries state in frozen dataclasses. A `BoardProvider` value is
  read by a `BoardClient`; there is no base class to subclass and no hidden
  state to inherit.
- **Not declarative.** A JSON or YAML provider definition was rejected. The
  judgement in a provider is in its normalizer — which employer field carries an
  arrangement, that silence is never `onsite`, how to build a posting URL a feed
  omits — and a path-mapping language cannot express that without becoming a
  language nobody asked for.
- **Greenhouse migrates first, before any new provider.** The framework is
  proven against a source with real data and real tests before eight providers
  depend on it. `ingest_greenhouse` and `GreenhouseClient` keep their public
  surface so the DAG, the discovery script, and the existing tests do not
  change.

## What research established

Facts from official documentation, checked 2026-09-03, that decide the shape of
the contract:

| Provider | Slug | Format | Pages | Description in list | States company |
| --- | --- | --- | --- | --- | --- |
| Greenhouse | path | JSON `jobs` | no | yes | per record |
| Lever | path | JSON array | `skip`/`limit` | yes | no |
| Ashby | path | JSON `jobs` | no | yes | no |
| SmartRecruiters | path | JSON `content` | `offset`/`limit` | **no, detail call** | per record |
| Workable | path | JSON `jobs` | no | with `details=true` | response level |
| Recruitee | subdomain | JSON `offers` | no | yes | per record |
| Personio | subdomain | XML `position` | no | yes | no |
| Pinpoint | subdomain | JSON `data` | no | yes | no |
| Polymer | path | JSON `items` | `page` | yes | per record |

Three consequences:

1. **Verification is not always possible.** Discovery confirms a guessed slug by
   reading the company the board states. Four feeds never state one. For those,
   discovery can report that a board answered, and cannot say whose it is. That
   is a new outcome, not a weaker confirmation.
2. **One provider needs a second request per posting.** SmartRecruiters lists
   postings without their text. A posting without a description cannot be
   normalized, so the client must be able to hydrate a record before the
   validator sees it.
3. **Two providers publish XML.** Validation and normalization read a mapping,
   so the client turns an element into one before handing it on, and nothing
   downstream knows the feed was XML.

## Target layout

```text
services/job-ingestion-service/job_ingestion/
  boards/
    __init__.py
    provider.py     BoardProvider, PageRead, Request
    client.py       BoardConfig, BoardClient
    discovery.py    candidate_slugs, belongs_to, discover, DiscoveryOutcome
    xml.py          element_to_record
    pipeline.py     configured_boards, ingest_board_source
    registry.py     PROVIDERS
  greenhouse/
    __init__.py     ingest_greenhouse
    provider.py     GREENHOUSE: BoardProvider
    records.py      unchanged
    normalizer.py   unchanged
    client.py       GreenhouseClient, GreenhouseConfig as thin aliases
    discovery.py    re-exports from boards.discovery
airflow/dags/
  board_ingestion.py   one DAG per registry entry
```

`greenhouse/client.py` and `greenhouse/discovery.py` survive only as import
paths. The discovery script and the tests import from them today, and keeping
the names is cheaper than touching every caller in the same change.

## The contract

```python
@dataclass(frozen=True, slots=True)
class Request:
    url: str
    params: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PageRead:
    records: tuple[RawRecord, ...]
    next_cursor: object | None = None


@dataclass(frozen=True, slots=True)
class BoardProvider[ProviderRecordT]:
    source_key: str
    display_name: str
    precedence: int
    default_base_url: str
    default_boards: tuple[str, ...]
    validator: JobRecordValidator[ProviderRecordT]
    normalizer: JobRecordNormalizer[ProviderRecordT]
    board_request: Callable[[str, str, object | None], Request]
    read_page: Callable[[str, httpx2.Response], PageRead]
    stated_company: Callable[[Sequence[RawRecord]], str | None]
    detail_request: Callable[[str, RawRecord], Request | None] | None = None
```

- `board_request(base_url, slug, cursor)` — the first call passes `None`. A
  provider with no pages ignores the cursor. What a cursor is belongs to the
  provider: an offset, a page number, an opaque token.
- `read_page(slug, response)` — turns one response into records and the next
  cursor, or raises `SourceResponseError`. This is where a JSON key is chosen
  or an XML element is walked. It does not inspect job fields.
- `stated_company(records)` — the company the board says these postings belong
  to, or `None` when the feed never says. Discovery reads it; nothing else does.
- `detail_request(base_url, record)` — when present, the client fetches it and
  merges the body into the record before the validator sees it. The configured
  host is passed so a regional override reaches detail requests as well as
  listing requests. Absent for every provider but SmartRecruiters.

`RawRecord` stays a `Mapping[str, Any]`. The client stamps `board` onto every
record, as Greenhouse does today, because a posting identifier is only unique
within the board that issued it.

## The client

`BoardClient(provider, config, http_client=None, sleeper=asyncio.sleep)`.
`BoardConfig` carries what `GreenhouseConfig` carries — boards, base URL,
timeout, attempts, backoff — plus `detail_concurrency` (default 4) for
hydration.

`fetch_board(slug)` walks `board_request` until `next_cursor` is `None` and
returns one `RawPage` holding every record on the board. Boards are small, and
one page per board is what the run and reconciliation already assume. The
retry rule is unchanged: transport failures and rate limits retry up to
`max_attempts`; any other non-success answer is a `SourceResponseError` and is
not retried.

Hydration, when the provider asks for it, runs after the walk with bounded
concurrency. A record whose detail cannot be fetched is dropped from the page
and recorded as a `RecordFailure` at the fetch stage, and the board is not
counted as fully read: a posting the run could not read looks exactly like one
that is gone, and reconciliation must not be allowed to conclude that.

`fetch_pages`, `failures`, `reached_the_end`, and the context-manager surface
are the ones `GreenhouseClient` has today, unchanged.

## Discovery

`candidate_slugs`, `strip_legal_form`, `belongs_to`, and `discover` move to
`boards/discovery.py` without changing. `discover(client, company)` asks
`client.provider.stated_company` instead of reading `company_name` itself.

`DiscoveryOutcome` gains `UNVERIFIABLE`: the board answered with records and
the feed states no company. It is reported alongside `WRONG_COMPANY`,
`NOT_FOUND`, and `UNREACHABLE`, and it never confirms anything. For Lever,
Ashby, Personio, and Pinpoint, adding a board stays a deliberate act by a
person who checked the careers page. The report says so rather than pretending
a guess is a finding.

`scripts/discover_boards.py` gains `--source <key>`, defaulting to
`greenhouse`, and builds its client from the registry.

## Pipeline and configuration

`ingest_board_source(provider, *, config=None, max_records, settings=None,
http_client=None)` is the body of today's `ingest_greenhouse`: record the run,
build the client, execute, fold in board failures, reconcile, complete the run.
`ingest_greenhouse` becomes a one-line call to it.

`configured_boards(provider, settings)` reads
`settings.source_config[provider.source_key]["boards"]` with the rules
established in #249: absent or empty means the shipped default, present but
not a list of names is refused. A `base_url` key in the same block overrides
the provider default, which is how a deployment reads Lever's EU host without
a code change.

`registry.PROVIDERS` is a tuple of every `BoardProvider`. It starts with
Greenhouse alone. Each provider PR adds one entry.

## Airflow

`airflow/dags/board_ingestion.py` iterates the registry and builds one DAG per
provider with `dag_id=f"{source_key}_ingestion"`, the retries, retry delay, and
timeout the Greenhouse DAG has today, and a schedule minute staggered by the
provider's position in the registry so nine hourly runs do not start together.
`airflow/dags/greenhouse_ingestion.py` is deleted; the DAG it defined is now
emitted by the factory under the same id.

The DAG structure tests are parametrised over the registry. `ALLOWED_CALLS`
gains the factory's names and loses the per-provider ones.

## What does not change

`contracts.py`, `pipeline.py`, `persistence.py`, `deduplication.py`,
`matching.py`, `reconciliation.py`, `runs.py`, `skills.py`, and
`vocabulary.py` are untouched. Every provider still writes under its own
source key, so per-source retirement and per-job withdrawal work exactly as
they do for two sources. Arbeitnow is not a tenant-board source and is not
touched.

## Testing

- The Greenhouse client, discovery, normalizer, and pipeline tests pass with
  the existing `board.json` fixture. Import paths may change; assertions do not.
- `tests/boards/` tests the framework against fake providers with
  `httpx2.MockTransport`: a single-request JSON provider, a paginated one, an
  XML one, and a hydrated one. Each covers the happy path, a board that cannot
  be read, and a rate limit.
- Discovery tests add the unverifiable case: a board that answers with records
  and a provider whose `stated_company` returns `None`.
- The XML reader is tested on a Personio-shaped document, including CDATA
  description blocks and repeated elements.
- DAG tests confirm `greenhouse_ingestion` still loads with the same schedule,
  retries, and timeout, and that every registry entry produces a DAG.

## Delivery

One issue and one pull request per row. The framework lands first so every
provider PR is small.

| Order | Change |
| --- | --- |
| 1 | #319 — framework, Greenhouse migrated, DAG factory |
| 2 | Policy: dated gate reviews for the eight; JazzHR and Talexio blocked |
| 3 | SmartRecruiters — states company, exercises hydration and paging |
| 4 | Recruitee — states company, carries `close_at` |
| 5 | Polymer — states company, page-based |
| 6 | Workable — response-level company name |
| 7 | Lever — unverifiable, `skip`/`limit`, EU host |
| 8 | Ashby — unverifiable, no documented `id` |
| 9 | Pinpoint — unverifiable, carries `deadline_at` |
| 10 | Personio — unverifiable, XML, no posting URL in feed |

Providers that state the company come first because their boards can be
discovered rather than typed, which is where the catalogue grows.

## Per-provider questions deferred to their own issues

- Ashby's documented schema lists no `id`; the provenance identifier may have
  to be the posting URL.
- Personio's feed carries no posting URL; the normalizer builds one from the
  slug and the position id, which the official integration sample does too.
- Lever and Ashby document no created or updated date; `published_at` may be
  empty for both.
- SmartRecruiters' identifiers are often not company names, so discovery will
  miss more than it finds there and the `company.name` field is what confirms
  a hand-typed one.

# Delivery Plan

This is the running answer to two questions: what is built, and what gets
decided before the next thing is built.

Work the phases in order. Before starting one, check that the decisions it
depends on have actually been made. The failure this order exists to prevent is
building against a choice nobody made on purpose.

Architecture and technology direction live in
[the project context](PROJECT_CONTEXT.md). The stored job shape lives in
[the canonical job contract](canonical-job-contract.md). This file only covers
sequence and open decisions.

## Where the project stands

| Phase | Tracker | State |
| --- | --- | --- |
| Foundation | — | Done |
| Canonical job model | #12 | Done |
| First ingestion path | #13 | Done |
| Jobs vertical slice | #14 | Not started |
| CV processing and matching | #15 | Not started |
| Analytics and production | #16 | Not started |

Built so far: a source-independent job catalog in PostgreSQL, and one working
ingestion path that fetches Arbeitnow postings, validates them, normalizes them,
deduplicates them, and stores them with provenance on an hourly schedule.

Nothing serves that data yet. There is no jobs API and no frontend.

## Decisions

### Settled

- **Simple matching before sophisticated matching.** Skill overlap, then
  TF-IDF, then embeddings, each evaluated before adoption. Recorded in the
  project context and reflected in #49, #53, and #63.
- **PostgreSQL and Alembic are the schema authority.** No second datastore
  without a demonstrated need.
- **Airflow orchestrates, it does not transform.** Pipeline logic stays in
  importable modules.
- **External job data is untrusted.** Validated at the boundary, never rendered
  as markup, never used to drive control flow.

### Open

Ordered by how expensive each is to reverse.

| Decision | Reversibility | Decide in |
| --- | --- | --- |
| What a skill is, and where the vocabulary comes from | Expensive: determines the skill tables, extraction, matching, and analytics | Phase B |
| Multi-source conflict policy: which source owns a canonical field | Expensive: schema and pipeline | Phase A.5 |
| Job lifecycle rule: when a job becomes expired or removed | Expensive: affects every query that filters on status | Phase A.5 |
| Where match scores live: computed per request or precomputed | Expensive: schema and pipeline | Phase D |
| Filter set, pagination style, sort order | Cheap: behind one query service | Phase A |
| Whether the job catalog is public or requires an account | Cheap: one dependency | Phase A |
| Authentication mechanism | Cheap: conventional and swappable | Phase C |
| CV file storage backend | Cheap: behind one interface | Phase C |
| Caching | Premature: needs measured read patterns | Phase E |

The skill model is the hinge. Free-text tokens, a curated list, and ESCO
produce three different databases and three different products, and #47, #48,
#49, #53, and the analytics tracker all consume whatever it decides.

## Phases

### Phase A — Prove the read path

Issues #31, #32, #33, #34, #35, #36, #37. Tracker #14.

Serve stored jobs through the API and render them: query service, listing
endpoint, detail endpoint, Next.js foundation, typed client, listing page,
browser test.

Decide only the cheap things: the filter set, the pagination style, and whether
browsing requires an account.

This phase goes first because nothing in it depends on an open expensive
decision, and because it forces the first real ingestion run. That run produces
the corpus every later decision needs.

**Exit:** a person can browse and filter real stored jobs in a browser, and the
catalog holds real postings rather than fixtures.

### Phase A.5 — Second source

Add a second provider, decide the conflict policy, and decide the lifecycle
rule.

Phase three built for this: sources are rows, one job may carry provenance from
several sources, and fingerprinting exists so the same posting from two boards
collapses into one job. A new provider needs a client, a validator, and a
normalizer, and no new orchestration.

What is not built is covered under [known gaps](#known-gaps) below. All three
must be resolved here, before a second source runs against real data.

This phase is early rather than late for two reasons. Deduplication is only
theoretically exercised while one source exists, and the cheapest moment to
discover that the fingerprint is too weak is before a matching engine and an
analytics dashboard read off the catalog. It also multiplies the corpus feeding
the Phase B decision, so the skill vocabulary is not derived from a single
job board.

**Exit:** two sources ingest concurrently, the same posting from both resolves
to one job, and a job absent from one source but present in another keeps the
correct status.

### Phase B — Decide the skill model

Reshapes #46, and consequently #47 and #48.

A design phase, not a build phase. Decide what a skill is, where the vocabulary
comes from, and how job text maps onto it, judged against the real corpus from
the previous phases rather than in the abstract.

**Exit:** an approved written spec, before any skill table exists.

### Phase C — Identity and CV intake

Issues #38 through #45.

Accounts, authentication, the CV upload policy, CV metadata, storage, the upload
endpoint, and PDF text extraction.

This follows Phase B because CV skill extraction needs the skill model settled.
Nothing before this point needs a user account to exist.

**Exit:** a signed-in user can upload a CV and its text is extracted and stored.

### Phase D — Matching

Issues #48 through #53.

Skill extraction on both sides, the overlap baseline, its evaluation, the
authenticated endpoint, the matching page, and the TF-IDF comparison.

**Exit:** a user sees ranked jobs with matched and missing skills, and the
ranking has been evaluated rather than assumed.

### Phase E — Analytics and production

Issues #54 through #65.

Analytics queries, endpoints, and dashboard; correlation logging, pipeline run
tracking, and readiness checks; ranking refinement and the embeddings
evaluation; the deployment baseline and the container release workflow.

Caching is decided here, against measured read patterns.

**Exit:** the application is deployed, observable, and reports job-market
insights from collected data.

## Known gaps

Found while reviewing the ingestion code. None affect the single-source
pipeline in use today; all three become defects the moment a second source runs.

- **Canonical fields are last-writer-wins.** Persistence overwrites every
  canonical field on update and no source precedence exists, so two sources
  describing one job would overwrite each other on every run.
- **No job is ever expired.** `expired` and `removed` exist in the vocabulary
  and are never assigned. Status is effectively write-once. With several
  sources the rule must read every provenance row for a job, because absence
  from one source does not mean the posting is gone.
- **The fingerprint is weaker across sources than within one.** Company names,
  location formats, and title abbreviations are consistent within a provider
  and not between providers, so cross-source duplicates may be missed.

## Issues that need rewriting before they are picked up

- **#46** asks for deterministic skill normalization and names no vocabulary.
  It cannot be implemented until Phase B decides one.
- **#43** presumes a CV storage abstraction. Whether an abstraction is
  warranted, rather than one concrete backend, is a Phase C decision.
- **#31** leaves cursor and offset pagination open. Phase A decides it.

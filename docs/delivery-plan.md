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
| Jobs vertical slice | #14 | Done |
| Second source | #93, #94, #95, #122 | Done |
| Skill model decision | #46 | Done |
| Identity and sessions | #38, #39, #40 | Done |
| CV processing and matching | #15 | Not started |
| Analytics and production | #16 | Not started |

Built so far: a source-independent job catalog in PostgreSQL, two ingestion
paths that fetch postings from Arbeitnow and from configured Greenhouse company
boards, validate them, normalize them, deduplicate them within and across
sources, and store them with per-source provenance, and a public read path over
the result. When two sources describe one posting, precedence decides which owns
each canonical field, and a posting is only withdrawn when a run that reached
the end of its source stops listing it and no other source still does. Jobs are
queried through one cursor-paginated service, served by a listing and a detail
endpoint, and rendered by a Next.js application with URL-backed filters and
infinite scroll. A browser test covers the three layers together against a
seeded catalog.

Not built: accounts, CV handling, skills, matching, and analytics.

The catalog has been proven against real postings, repeatedly, but only in
throwaway databases. No environment holds them persistently yet, which is the
one part of the Phase A exit criterion still outstanding and needs a decision
about where that environment lives rather than more code. Only Arbeitnow is
scheduled; Greenhouse runs on demand, because scheduling it without somewhere
to schedule it into would be scheduling into nothing.

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
- **The job catalogue is public.** Anonymous visitors read the whole catalogue,
  listings and detail pages alike. Authentication gates applying and the
  personalized features, which additionally require a completed candidate
  profile.
- **A candidate profile is reachable two ways.** Uploading a CV and extracting
  the profile from it, or manual step-by-step onboarding. Neither is the
  fallback for the other; both must produce the same profile.
- **Listings are cursor-paginated, twenty per batch.** The order is
  `published_at DESC NULLS LAST, id DESC`, which is total, so every row has one
  predecessor and infinite scroll never repeats or skips a job. A cursor is
  meaningful only inside the filter set that produced it; changing a filter
  restarts pagination.
- **The read path streams nothing on the listing route.** A route-level
  loading file makes the route send a fallback first, and swapping the real
  content in needs client JavaScript, so the page never rendered without it.
  The catalog is public, so it renders complete on first byte instead.
- **Cursors are opaque and versioned.** Base64, unsigned, refused rather than
  reset when unreadable. Clients never construct one.
- **The frontend types the API by hand.** Generating them needs a cross-stack
  CI job or a schema snapshot; instead the backend asserts the exact fields,
  nullability, and vocabulary members of every served schema against literals.
- **Phase A ships five filters:** company, location, workplace type, employment
  type, and free-text search on title. Source filtering waits until a second
  source exists to make it meaningful. Relevance-ranked search is a different
  sort order and therefore a different cursor, so it stays out of Phase A.
- **A source owns a canonical field by rank, and silence never wins.** Sources
  carry a precedence. An unstated value never overwrites a stated one whatever
  the rank, so a source that omits a field cannot erase it. Between two stated
  values the higher rank decides, and equal ranks go to the incoming one.
- **Two postings are the same posting by employer and title, confirmed by
  place and prose.** The match key blocks candidates on employer and title
  alone; a candidate is only merged when the cities agree and the descriptions
  read the same. Location is deliberately outside the key, because the two
  sources write places differently for the same job.
- **Absence only means gone when a run was entitled to say so.** A run is
  processing-complete when it handled everything it fetched, and
  source-exhausted only when it also reached the end of the source without a
  budget cap, a skipped board, or a failure. Only exhausted runs may withdraw.
  A stated expiry date needs no such run: a date the posting asserts about
  itself is a fact, while absence is an inference.
- **The skill model is hybrid.** Known skills normalize to canonical
  concepts, ESCO is an optional mapping layer where confident, and legitimate
  unknown skills are preserved. Matching combines pretrained multilingual
  embeddings with explicit skill overlap and structured profile signals. Job
  embeddings are precomputed at ingestion, candidate embeddings from the
  canonical profile, and the first version is a measurable baseline rather than
  a trained model. Decided against measurement rather than in the abstract:
  [the decision](superpowers/specs/2026-08-24-skill-model-decision.md),
  [the evidence](skill-model-measurement/results.md).
- **A posting is retired per source and withdrawn per job.** An unseen posting
  retires that source's provenance row. The job itself is only marked removed
  once no un-retired provenance remains.

### Open

Ordered by how expensive each is to reverse.

| Decision | Reversibility | Decide in |
| --- | --- | --- |
| Where match scores live: computed per request or precomputed | Expensive: schema and pipeline | Phase D |
| How applying works: a gated redirect, or a tracked application record | Expensive if tracked: new entity, migrations, and endpoints | Phase C |
| What makes a candidate profile complete, and what manual onboarding asks for | Expensive: the skill question inside it is the Phase B decision | Phase B, then C |
| CV file storage backend | Cheap: behind one interface | Phase C |
| Server-side caching | Premature: needs measured read patterns | Phase E |
| What makes an unknown skill legitimate enough to store | Expensive: without it the design re-admits the 85% junk that got free text rejected | Before #46 ships |
| Whether v1 serves German now that the encoder is multilingual | Cheap to decide, expensive to retrofit later | Phase C |

The skill model was the hinge and is now decided. It went to a hybrid because
each single option failed differently and the failures were measured: free text
found almost everything by matching almost everything, at 0.151 precision, and
the two disciplined vocabularies missed more than half. Manual onboarding
follows from it — a candidate picks canonical concepts with a free-text escape,
rather than a bare box or a taxonomy picker.

The client-side cache behind infinite scroll is not this table's kind of
decision. Holding fetched batches so scrolling back up costs no request is part
of building the listing page. Server-side caching is the deferred one.

## Phases

### Phase A — Prove the read path — done

Issues #31 through #37, plus #106, #108, and #113. Tracker #14.

Query service, listing and detail endpoints, Next.js foundation, typed client,
listing page, detail page, and a browser test over all three layers.

It did what the phase was for. Running the pipeline against the live board for
the first time found two defects that fixtures could not: escaped provider
markup was being turned into live markup rather than removed (#104), and the
workplace arrangement was being read from the one field that states it least
often (#108). Rendering real postings found two more: excerpts that were
headings rather than prose, and a badge shown on every card that said nothing.

**Exit:** met, except that no persistent environment holds the real postings.
That is a deployment decision rather than a coding one.

### Phase A.5 — Second source — done

Add a second provider, decide the conflict policy, and decide the lifecycle
rule.

Phase three built for this: sources are rows, one job may carry provenance from
several sources, and fingerprinting exists so the same posting from two boards
collapses into one job. A new provider needs a client, a validator, and a
normalizer, and no new orchestration.

Three gaps found while reviewing the ingestion code had to close first, and
did: canonical fields were last-writer-wins (#93), no job was ever expired
(#94), and the fingerprint was weaker across sources than within one (#95).

This phase is early rather than late for two reasons. Deduplication is only
theoretically exercised while one source exists, and the cheapest moment to
discover that the fingerprint is too weak is before a matching engine and an
analytics dashboard read off the catalog. It also multiplies the corpus feeding
the Phase B decision, so the skill vocabulary is not derived from a single
job board.

Issues #93, #122, #95, and #94, worked in that order. Precedence first,
because a merge rule is needed before two sources may write one row. Then the
Greenhouse client, validator, and normalizer over explicitly configured boards,
with discovery deferred to #120. Then cross-source matching, then lifecycle.

**Exit:** met. Both sources ingest into one catalog, a posting listed by both
resolves to a single job carrying two provenance rows, and a job absent from one
source keeps its status while another still lists it.

The order was not cosmetic. Writing the precedence tests surfaced a posting that
two sources placed in different cities, and matching refused it outright, which
is why #93 had to precede #95. Measuring #95 against a labelled set rather than
by inspection mattered too: the first count of duplicate pairs was wrong, and
the corrected set of 29 is what the rule was tuned against. It recovers 24 of
them, up from none, with no wrong merges. The remaining five differ by more than
the rule is willing to overlook.

The lifecycle split earned itself immediately. A run capped at five records is
processing-complete and not source-exhausted, and against a real board that
single distinction was the difference between withdrawing twenty-four open jobs
and withdrawing none.

### Phase B — Decide the skill model — done

Reshapes #46, and consequently #47 and #48.

A design phase, not a build phase. Decide what a skill is, where the vocabulary
comes from, and how job text maps onto it, judged against the real corpus from
the previous phases rather than in the abstract.

That corpus does not exist yet. Every run so far has been verified in a database
that was then deleted, so the phase begins by producing one: a full ingest from
both sources whose measurements are written down and committed, rather than the
database itself being kept. What has to be measured is coverage. A curated list
either captures most of the skill mentions in real postings or it does not, and
the shape of what it misses decides between a curated list, free text, and a
taxonomy. Measuring that needs a snapshot, not a hosted environment, so this
phase does not wait on the deployment decision.

**Exit:** met. The spec is
[the skill model decision](superpowers/specs/2026-08-24-skill-model-decision.md),
approved before any skill table exists.

The phase cost more than a design phase normally would, because it had to build
its own evidence first: a 3354-posting corpus, 80 postings annotated twice by
independent annotators, 1053 contested spans adjudicated blind, and three
vocabularies scored against the result. What that bought is a decision with
numbers behind it rather than three plausible arguments.

It also produced findings the decision rests on. Two annotators following one
frozen guide named the same span differently 36.7% of the time, which is why
canonical concepts are not optional. 184 hand-written surface forms beat 65850
ESCO labels by 12.7 points of recall, which is why ESCO is a mapping layer
rather than the vocabulary. And 28 of the 38 mentions no arm found were named
products and standards, which is why unknowns are preserved.

### Phase C — Identity and CV intake

Issues #38 through #45, plus the candidate profile and applying.

Accounts, authentication, the CV upload policy, CV metadata, storage, the upload
endpoint, and PDF text extraction. On top of those: the candidate profile
itself, the manual onboarding path into it, the rule that decides when it counts
as complete, and what applying to a job actually does.

This follows Phase B because both routes into a profile need the skill model
settled. CV extraction has to write skills somewhere, and manual onboarding has
to ask for them with some control. Nothing before this point needs a user
account to exist, because the catalogue is public.

Three tracks, and only the third is serial. Identity comes first and blocks
nothing: #38, #39, #40. The profile track starts once the user row exists and
runs beside the CV work, because skills do not gate completeness. The CV track
waits on the session.

**Identity is done.** Accounts, argon2id hashing, registration, login, the
current-user dependency, and logout here versus everywhere. Sessions are a
token in an HttpOnly cookie, which is as much a rendering decision as a
security one: a token held in JavaScript cannot be read by a server component,
so every personalized page would have become a client fetch and undone the
first-byte rendering Phase A chose. Revocation is a version claim on the user
row — ordinary logout clears one device, while a password change or a disabled
account ends every session.

What review caught there is worth carrying into the remaining tracks, because
none of it was visible in a passing test suite at 100% coverage: a validation
error returned the submitted password in the response body, a shared exception
object leaked request state on every rejection, and password hashing ran on the
event loop where ten concurrent logins stalled the public catalogue for the best
part of a second.

**Exit:** a signed-in user has a complete candidate profile, reached by either
route, and can apply to a job. Identity is met; the profile and CV tracks
remain.

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

## Known gaps — closed

Three gaps found while reviewing the single-source ingestion code, each
harmless until a second source ran and a defect the moment one did. All three
closed in the second-source phase, and the rules that replaced them are in
[the canonical job contract](canonical-job-contract.md).

- **Canonical fields were last-writer-wins** (#93). Every update overwrote
  every field and no source precedence existed. Replaced by rank, with silence
  never overwriting a stated value.
- **No job was ever expired** (#94). `expired` and `removed` existed in the
  vocabulary and were never assigned. Replaced by per-source retirement,
  withdrawal only when no source still lists the job, and only from runs that
  reached the end of their source.
- **The fingerprint was weaker across sources than within one** (#95). Company
  names, location formats, and title abbreviations are consistent within a
  provider and not between providers. Replaced by a two-stage rule that blocks
  on employer and title and confirms on place and prose.

## Open questions carried forward

- **#98, what applying does.** A gated redirect or a tracked application
  record. The second is a new entity and a migration, so it is a Phase C
  decision rather than an implementation detail.
- **Where a persistent environment lives.** Needed before the catalog can hold
  real postings outside a test run. It is not needed to decide the skill model,
  which needs a measured snapshot rather than a running system.
- **Whether Greenhouse gets scheduled, and how boards are found.** Only
  Arbeitnow runs on a schedule. The board list is three names in code until
  #120 replaces it with discovery, and scheduling a hand-written list into a
  database nobody keeps would prove nothing.
- **Source filtering on the listing.** Deferred in Phase A on the condition
  that a second source exists to make it meaningful. It now does, so the
  condition is met and the deferral is a choice rather than a consequence.

## Issues that need rewriting before they are picked up

- **#46** asked for deterministic skill normalization and named no vocabulary.
  Phase B has now decided one, so it is rewritten as the canonical-concept
  model: concepts, surface forms, aliases, and the gate that decides which
  unknown skills are legitimate enough to store.
- **#43** presumes a CV storage abstraction. Whether an abstraction is
  warranted, rather than one concrete backend, is a Phase C decision.

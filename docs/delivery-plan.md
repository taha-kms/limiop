# Delivery Plan

This is the running answer to two questions: what is built, and what gets
decided before the next thing is built.

Work the phases in order. Before starting one, check that the decisions it
depends on have actually been made. The failure this order exists to prevent is
building against a choice nobody made on purpose.

Architecture and technology direction live in
[the project context](PROJECT_CONTEXT.md). The stored job shape lives in
[the canonical job contract](canonical-job-contract.md), and the gate for adding
or blocking providers lives in [the job source policy](job-source-policy.md).
This file only covers sequence and open decisions.

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
| Service extraction | #160–#168, #171 | Done |
| Skills at ingestion | #187–#194, #199, #202–#205 | Done |
| CV processing and matching | #15 | Done |
| Analytics and production | #16 | Done |

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

A local environment now holds the catalog persistently, on an external Docker
volume that survives `docker compose down -v`, and both sources are scheduled
hourly. Postings carry canonical skills: extraction runs inside the transaction
that stores each posting, against the alias table the backend publishes into the
shared database, and 6,406 skill rows sit against 456 of the 1,252 stored
postings.

## Decisions

### Settled

- **Simple matching before sophisticated matching.** Skill overlap, then
  TF-IDF, then embeddings, each evaluated before adoption. Recorded in the
  project context and reflected in #49, #53, and #63.
- **PostgreSQL and Alembic are the schema authority.** One PostgreSQL has two
  migration chains: `platform/db` owns tables touched by both deployables and
  the backend owns its private tables. No second datastore without a
  demonstrated need.
- **Airflow orchestrates, it does not transform.** Pipeline logic stays in
  `services/job-ingestion-service`, and Airflow never depends on the backend.
- **Job ingestion is a separate deployable.** Fetching, validation,
  normalization, deduplication, reconciliation, and persistence differ from API
  behavior, so they live in `services/job-ingestion-service`. The backend is
  only the API. A data-access service was rejected because storage does not
  define a behavior boundary and the catalog updates must remain atomic.
- **External job data is untrusted.** Validated at the boundary, never rendered
  as markup, never used to drive control flow.
- **The job catalogue is public.** Anonymous visitors read the whole catalogue,
  listings and detail pages alike. Authentication gates the personalized
  features, which additionally require a completed candidate profile.

  This bullet used to say that authentication gates applying too, and that half
  was unenforceable by the other half. `application_url` is a required field on
  every served job, both job endpoints take no user dependency, and both the
  listing card and the detail page render it as a link. The URL is in every
  anonymous response, so a gate on applying could only ever have been a prompt
  drawn on our own page, never access control. Settling #98 chose which half
  survives: the public catalogue is shipped, tested, and load-bearing, and the
  gate was neither built nor buildable without withholding a field the same
  sentence promises to publish.
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
- **A term is promoted by being read, never by being frequent.** The
  observation inbox now holds 7,736 distinct terms with per-employer counts,
  and they settle the question #152 asked. Ranked by employers, the top thirty
  contain exactly one skill: `Senior` leads at 35 and names a seniority, while
  `Python` sits at 18 and is the only unambiguous technology above it. Eleven
  ordinary words, four places and three job titles sit in between, so no
  threshold separates them and none can.

  The gate stays closed to automatic admission. A term becomes a concept when a
  person reads it in context and publishes it in a new alias version, which is
  how `2026.08.29.2` added five. What changed is that the review has an input
  instead of a corpus snapshot nobody can re-run. Recorded in
  [the observations](skill-model-measurement/candidate-observations.md).

- **Unknown skills are closed to matching and open to observation.** The
  committed evidence cannot score a permissive rule against identifiable
  unknowns and labelled junk, so no unresolved candidate reaches `job_skills`
  or becomes a concept. Each one is still recorded in `job_skill_mentions`,
  which nothing matches against, carrying the raw and normalized forms, the
  job, per-posting occurrence counts and timestamps, and both the extractor
  version and the vocabulary version under which resolution failed. Recording
  an observation is not admitting a skill, and it is what makes the closed rule
  temporary: the evaluation failed for want of candidates linked to postings
  and employers, and live ingestion accumulates exactly those. The gate is
  re-decided against production observations rather than a second
  hand-annotated corpus. Recorded in
  [the gate evaluation](superpowers/specs/2026-08-25-job-skills/gate-evaluation.md).
- **A measurement commits its evidence, not only its findings.** Any
  measurement a decision rests on must commit the records behind it: the text
  that was scored, the labels, and the keys needed to join them back together.
  Aggregate findings alone are not reproducible and not extensible.

  This was learned twice in one day. The skill-model corpus committed its
  conclusions — 0.151 precision for free text, 184 surface forms beating 65850
  ESCO labels by 12.7 recall points, 28 of 38 misses being named products —
  but not the postings, the employer map, or the join from adjudicated
  rejections back to candidate text. As a result the unknown-skill gate could
  not be scored at all, and the extractor can only be scored against the 14 of
  78 gold postings still recoverable from the live catalog. The other 64 have
  expired from the board and are gone permanently.

  Where the text cannot be committed — licensing, size, or personal data — a
  reproducible retrieval path and a content hash must be, so a future reader
  can tell whether what they fetched is what was scored. Storing a hash without
  the means to fetch the content, which is what happened here, is not enough.

- **Crossing the session boundary replaces the document.** Every page renders
  on the server from the session cookie, and the router cache holds entries
  built before that cookie existed — including, for a visitor arriving from a
  redirect, an entry for the page they are being sent back to. Signing in and
  out therefore replace the document rather than navigating within it. Found by
  the browser test, not by reasoning about it.

- **A measurement is only as good as the corpus it runs on.** Half the stored
  catalog comes from one employer, whose postings share a long boilerplate
  blurb, so any per-posting statistic measures who is hiring rather than what is
  true. `interpretability` appears in 500 postings and one employer. Counts and
  samples are reported per employer, and a sample is drawn at most once per
  employer. Established in
  [the alias-collision audit](skill-model-measurement/alias-collision-audit.md),
  which found three verdicts reversed by the correction.

- **Extraction is enrichment, and enrichment never fails a record.** Skills are
  written inside the transaction that stores the posting, so a posting never
  commits with half of them, but a failure while writing them rolls back only
  the skills and never joins the run's failures. A failure there would make the
  run neither processing-complete nor source-exhausted, and so would stop
  reconciliation withdrawing a posting over a problem that says nothing about
  whether the posting is gone.

- **Embeddings were measured and not adopted.** NDCG@5 0.7896 against the
  baseline's 0.8055, on the same corpus and metrics, for 5.1 GB of runtime and
  4.84 seconds of model load per process. Precision@1 is identical, so the
  encoder buys nothing at the top of the ranking and loses below it.

  Two reasons beyond the number. It scores partial credit for nearness, which
  is not the question — a recruiter's skills sit close to a seller's, and the
  model cannot know the candidate lacks them. And it makes a meaningless
  profile look confident: the candidate holding one generic concept is offered
  a 0.77 match where the baseline offers 0.33. A wrong answer that looks
  confident is the failure this project has now met three times.

  This closes #131 as well. There is nothing to precompute for a matcher that
  was not adopted, and the storage, versioning, lifecycle and re-embedding costs
  it named all buy a worse ranking. Recorded in
  [the evaluation](matching-evaluation/embeddings.md).

- **TF-IDF was measured and not adopted.** Same corpus, same metrics: NDCG@5
  0.8156 against the baseline's 0.8055, precision@1 identical, latency 0.471 ms
  against 0.271 ms. Neither number decides it. A gain of 0.0101 across six
  candidates is two of them moving, on a corpus whose own write-up said in
  advance that it could not resolve a difference that size.

  What decided it is that the score stops agreeing with the explanation. A
  candidate holding every skill a posting asks for is shown "3 of 3 skills" and
  a cosine score of 0.84, because cosine normalises by the candidate's own
  vector and so penalises knowing more than was asked — the asymmetry the
  baseline exists to refuse, returning as a number nobody can check. This
  product promises matched and missing skills, not a similarity, and a score
  that cannot be read back to the list beside it is a different product.
  Recorded in [the comparison](matching-evaluation/tfidf.md).

- **A profile with fewer than three skills is not ranked.** Not clamped, not
  ordered arbitrarily: nothing is returned.

  The evaluation measured why. A corpus candidate holding one concept —
  Communication skills — scored 0.0 on every ranking metric while still being
  served a confident-looking 0.33 match, and that single case is the entire gap
  between the baseline's reported 0.8055 and the 0.9666 the other five average.
  A wrong answer that looks considered is worse than an empty one.

  The evidence establishes that one skill is too few, not where the line sits.
  Three is a judgment inside that bound: it also refuses a two-concept profile,
  which fails the same way less obviously, and every real candidate in the
  corpus holds four. It replaces `PROVISIONAL_MINIMUM_USABLE_SKILLS`, which the
  design spec called a formality rather than a threshold and which had no
  production caller.

- **Matches are not cursor-paginated.** The listing is, and matching is not,
  because the two orders are different kinds of thing. A listing position comes
  from stored columns under a total order; a match position comes from a score
  computed per request against a profile the candidate can edit and a catalogue
  re-extracted hourly. A cursor into an order that moves underneath it is a
  cursor that lies, and the listing's own rule already limits a cursor to the
  filter set that produced it. Matches return a bounded page and say how many
  were ranked.

- **Match scores are computed per request.** The baseline is a set
  intersection over the handful of canonical concepts a posting carries, so
  computing one costs less than reading a stored one would.

  Precomputing was priced as the expensive option and it is worse than its cost
  suggests. A stored score is keyed on a candidate and a job, and three
  existing write paths invalidate it: the candidate editing their profile, the
  hourly ingestion re-extracting a posting's skills, and a new alias table
  being published, which re-extracts the whole catalogue. Two of those run
  unattended. A cache that three unattended writers invalidate is a
  correctness problem bought with a table.

  This is revisited against a measured read pattern, not before. Nothing in the
  ranking is stored, so reversing it adds a table rather than changing one.

- **The score is coverage of the job's skills, not similarity.** Matched
  concepts over required concepts: the share of what a posting asks for that
  the candidate already has. Set similarity divides by the union instead, which
  scores a broad candidate below a narrow one for the same job, and a candidate
  who knows more than was asked is not a worse fit. Skills the posting did not
  ask for are never held against anybody.

  A posting naming no skills scores zero rather than one. There is no share of
  nothing, and scoring silence as a perfect match would rank every posting whose
  extraction found nothing above every posting that matched genuinely.

- **Applying is a link, and nothing is recorded.** The candidate follows the
  source's own `application_url`. There is no application entity, no status, and
  no endpoint on the path.

  A tracked record was refused on product grounds rather than cost — the
  migration is cheap. All three benefits offered for it are unwritten or
  contradicted. Analytics is contradicted: #54's first acceptance criterion is
  that counts derive only from canonical stored jobs and skills, and every
  insight the project context lists is computed from job data rather than
  candidate behaviour. Suppressing an already-applied job is not in Phase D's
  exit, and building it would widen "a cursor is meaningful only inside the
  filter set that produced it" to include the viewer, which settles the still
  open server-caching row by side effect. An application history could not be
  honestly named: SkillSync would be listing link renders under a heading that
  claims applications.

  Every status a tracked record would carry — submitted, screening,
  interviewing, offered, rejected — is a state of an applicant tracking system
  that never reports back. The plan already refuses to type an inference as a
  fact.

  There is not even a click to record. Under a plain link the navigation happens
  in the browser to a third-party origin with no SkillSync route on the path, so
  the signal is never produced rather than discarded. Manufacturing one would
  take a redirect route or a click beacon, and reversing this decision means
  reopening that, not merely adding a table. The cost is named: no record of who
  was sent where exists for the period this runs, and it cannot be backfilled.

- **A posting is retired per source and withdrawn per job.** An unseen posting
  retires that source's provenance row. The job itself is only marked removed
  once no un-retired provenance remains.

### Open

Ordered by how expensive each is to reverse.

| Decision | Reversibility | Decide in |
| --- | --- | --- |
| What makes a candidate profile complete, and what manual onboarding asks for | Expensive: the skill question inside it is the Phase B decision | Phase B, then C |
| CV file storage backend | Cheap: behind one interface | Phase C |
| Server-side caching | Premature: needs measured read patterns | Phase E |
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

**Exit:** met. A local environment now holds the real postings on an external
Docker volume, proven by writing a job, running `docker compose down -v`, and
reading it back. Moving that environment to a VPS is a deployment decision
rather than a coding one.

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

### Service extraction — done

Issues #160 through #168, plus #171.

Job ingestion moved out of the backend and into
`services/job-ingestion-service`. Shared catalog and skill models moved to
`platform/db`, with one migration chain for shared tables and another for
backend-owned tables in the same PostgreSQL database. Airflow now depends on
the ingestion service and has no dependency on the backend.

This phase sits before Phase C rather than inside it. CV intake and candidate
profiles land in the backend, and they should land in a deployable whose only
responsibility is the API.

**Exit:** met. Ingestion runs as its own deployable, Airflow calls it without
the backend, both Alembic chains build one database in ownership order, and the
backend is only the API.

### Phase B.5 — Skills at ingestion — done

The alias table, the shared extractor, the two skill tables, and extraction
wired into the pipeline. Issues #187 through #194, #199, and #202 through #205.

Three things this phase found that measurement alone would not have:

- **The vocabulary, not the extractor, was the precision problem.** The first
  run over real postings scored 0.1417. Reading all 182 surface forms against
  985 postings from 295 employers found 50 that read as ordinary English —
  `own`, `flexible`, `management`, `platform`, `safety` — and removing them cost
  none of the 455 gold labels the vocabulary could resolve.
- **The committed gold set cannot score a vocabulary change.** All 14 of its
  recoverable postings come from one employer, it annotates each term once per
  posting while the extractor fires on every occurrence, and 184 of the 190
  matches it credits are fragments of longer annotated phrases.
- **The observation inbox cannot fill.** The extractor matches a vocabulary and
  cannot see a term outside it, so the table the unknown-skill gate depends on
  takes zero rows until #205 generates candidates.

### Phase C — Identity and CV intake

Issues #38 through #45, plus the candidate profile and applying.

Accounts, authentication, the CV upload policy, CV metadata, storage, the upload
endpoint, and PDF text extraction. On top of those: the candidate profile
itself, the manual onboarding path into it, the rule that decides when it counts
as complete. What applying does is settled: the candidate follows the source's
own link, and nothing is recorded.

This follows Phase B because both routes into a profile need the skill model
settled. CV extraction has to write skills somewhere, and manual onboarding has
to ask for them with some control. Nothing before this point needs a user
account to exist, because the catalogue is public.

Three tracks, and only the third is serial. Identity comes first and blocks
nothing: #38, #39, #40. The profile track starts once the user row exists and
runs beside the CV work, because skills do not gate completeness. The CV track
waits on the session.

**Identity is done, in both halves.** Accounts, argon2id hashing, registration,
login, the current-user dependency, and logout here versus everywhere — and
since #210, the routes that let anyone reach them. The API half shipped first
and sat unreachable for weeks, which is worth remembering: a backend feature
with no way in is not a shipped feature, and the plan recorded identity as done
throughout. Sessions are a
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
route, and can apply to a job. Applying already works for everyone, because it
is a link on a public page. Identity is met in both halves now — the API since
#38–#40, the browser since #210 — so a visitor can register, sign in, reach
their profile, and sign out. The CV route into a profile remains.

### Phase D — Matching — done

Issues #213 through #218, refining #47 through #53.

Both sides of the join already existed when the phase opened: `job_skills` since
#189 and `candidate_profile_skills` since the onboarding picker, keyed on the
same concepts under the same alias version. The baseline was a set intersection
rather than a subsystem, and most of the phase was deciding what the number
means and proving it.

Three findings the phase turned on:

- **A candidate with one generic skill gets a confident ranking worth nothing.**
  Measured, not suspected: the corpus candidate holding only Communication
  skills scored 0.0 on every ranking metric while being served a 0.33 match, and
  that single case is the whole gap between the baseline's 0.8055 and the 0.9666
  the rest average. It is why a profile with fewer than three skills is refused
  rather than ranked.
- **TF-IDF wins on the metrics and loses on the product.** It gains 0.0101
  NDCG@5 and breaks the agreement between the score and the explanation: a
  candidate holding every skill a posting asks for sees "3 of 3 skills" beside
  0.84.
- **A CV and the picker write the same table.** Two skill tables would have made
  the settled decision that both routes produce the same profile false at the
  schema level, so the row records which route wrote it instead, and a
  hand-picked skill outranks an inferred one.

**Exit:** met. A signed-in candidate sees ranked jobs with matched and missing
skills, and the ranking was evaluated against a committed corpus before it was
served rather than after.

### Phase E — Analytics and production — done

Issues #54 through #65, plus #120, #129, #152, #205 and #208.

Analytics queries, endpoints, and a dashboard; correlation logging, pipeline
run tracking, and readiness checks; the deployment baseline and the container
release workflow. Ranking refinement and the embeddings evaluation both ended
in a rejection, which is what refinement looks like when the measurements say
no.

Four things this phase found that were not on anyone's list:

- **A rate limit was the one transient failure neither client retried.** Two
  runs against the same board ingested 1450 and then 1150 records, so how much
  of a source was read depended on how the provider felt about the traffic.
- **The observation inbox was structurally empty**, because the extractor
  matches a vocabulary and cannot see a term outside it. It now holds 28,172
  observations over 7,736 terms, which is what let the promotion question be
  answered.
- **Frequency cannot promote a term.** Ranked by employer, the top thirty
  observations contain exactly one skill.
- **Board discovery cannot read a board out of stored data.** The aggregator
  rewrites every application URL to its own page, so the only input is the
  company's name — and what makes guessing safe is verifying the answer against
  the company the board states.

Ranking was refined by measuring three matchers and keeping the simplest.
TF-IDF gains 0.0101 NDCG@5 and breaks the agreement between the score and its
explanation; embeddings lose 0.0159 and cost 5.1 GB. No signal was added,
because none was justified — which is what "improve only through measured
changes" means when the measurements say no.

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

- **How boards are found.** Both sources are scheduled hourly now. The board
  list is still three names in code until #120 replaces it with discovery.
- **How unknown skills ever get observed.** `job_skill_mentions` is wired,
  tested, and structurally empty: the extractor matches a vocabulary and cannot
  see a term outside it, and no published alias table has an ambiguous surface
  form. The gate decided in #190 stays closed and stays undecidable until #205
  generates candidates the vocabulary does not already contain.
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

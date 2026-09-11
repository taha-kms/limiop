# Automatic board registry — design

Date: 2026-09-03. Epic: #329.

## Problem

The tenant-board providers read a list of boards, and a person writes that
list. Discovery (#238) finds and verifies candidates and prints a report;
polling them (#249) means copying slugs into `SKILLSYNC_SOURCE_CONFIG`.
Greenhouse ships three boards in code. Polymer and Pinpoint ship none, so
neither ingests anything until someone does that by hand, and nothing ever
notices a board that went away or started answering for another company.

The goal is that for Greenhouse, Polymer, and Pinpoint the whole loop runs
without a person: discover boards, verify each one belongs to the company it
was guessed from, register it, poll it, and periodically rediscover, retire,
and re-verify.

## Decision

A database-backed registry that discovery writes and ingestion reads, with
one scheduled discovery run per provider beside the hourly ingestion run.

- **A table, not a config file.** Every board row carries how it was verified
  and when. That is what makes automatic registration safe to run unattended:
  a wrong decision is visible, dated, and reversible, and a row that was
  established by a person is marked so nothing overwrites it.
- **Discovery and ingestion stay separate runs.** Discovery guesses, which is
  cheap to get wrong and must be budgeted; ingestion writes postings, which
  must never happen for an unverified board. Two runs, two schedules, one
  table between them.
- **Verification is provider-specific; registration is not.** What counts as
  evidence differs per provider and lives in its provider module. What is done
  with the evidence is one rule for all of them.
- **Guesses are probes, never proof.** A slug derived from a company name is
  the address to check. It confirms nothing on its own for any provider.

Rejected: writing discovery results back into configuration (no history, no
evidence, couples ingestion to the scheduler), and probing during ingestion
(no budget, and a wrong-company probe sits in the run that writes postings).

## The registry

Table `job_boards` in `platform/db`, migration `0004_job_boards`.

| Column | Meaning |
| --- | --- |
| `source_id` | the provider (`job_sources`) |
| `slug` | board name, unique per source |
| `company_id` | set once verified; null for candidates and negatives |
| `status` | `candidate`, `confirmed`, `named`, `wrong_company`, `not_found`, `unreachable`, `inactive`, `blocked` |
| `evidence` | jsonb: `kind`, `found_company`, `website`, `checked_at`, and whatever the kind needs |
| `discovered_at`, `verified_at`, `last_checked_at`, `last_polled_at` | timestamps of the obvious events |
| `last_posting_count`, `consecutive_failures` | poll outcome tracking |
| `pinned` | set by an operator; automatic runs report but never change a pinned row |

Polled statuses: `confirmed`, `named`, and any `pinned` row. `wrong_company`
and `blocked` rows are never polled and never re-guessed; they exist so the
same wrong slug is not tried again next week.

Evidence kinds: `provider_name` (the feed states the company), `site_title`
(the careers site states it), `website_link` and `website_redirect` (the
company's own website points at the board), `operator`.

The migration seeds Greenhouse's three shipped boards as `pinned`, so the
switch from configuration to registry stops nothing.

## Discovery run

One run per provider, scheduled daily and staggered, with a per-run probe
budget (default 200) and a politeness delay between requests.

1. **Seed.** Catalogue companies with no row for this provider, plus rows due
   for a recheck: `unreachable` next run, `not_found` after a week,
   `confirmed` and `named` after a month.
2. **Candidates.** The existing slug generation (`candidate_slugs`). For
   Pinpoint the same candidates are tried as subdomains.
3. **Probe and verify.** The provider's own rule, below.
4. **Register.** Upsert the row with status, evidence, `company_id` when
   verified, and `last_checked_at`. Negatives are stored too.

The run summary reports counts per outcome, and the budget is what bounds a
run against a catalogue of thousands of companies.

## Verification per provider

**Greenhouse and Polymer.** The feed states the company on every record
(`company_name`, `organization_name`). `stated_company` compared with
`belongs_to` confirms the slug. Evidence kind `provider_name`. This is what
discovery already does; the change is that the outcome is stored.

**Pinpoint.** The feed states nothing, so two layers:

- *Identity.* The careers site states its own name: the page title
  (`Jobs at Pinpoint | Pinpoint Careers`) and the RSS channel title
  (`Careers at Pinpoint`). A name matching the company under `belongs_to`
  registers the board as `named`. The tenant chose that name, which is the
  same act as Polymer's tenant choosing `organization_name`, so `named` is
  polled.
- *Corroboration.* When the company's website is known, its home page and
  its `/careers` and `/jobs` pages are fetched, respecting `robots.txt`, and
  a link, redirect, or embed of `{subdomain}.pinpointhq.com` upgrades the row
  to `confirmed` with the URL where it was seen. At most three pages per
  company, no posting extraction, an identifying user agent.

A guess that answers but states another name is `wrong_company`. A guess
that answers and states nothing usable stays `candidate` and is not polled.

## Company websites

Corroboration needs the company's official website, which the catalogue does
not hold today. Three keyless strategies, in order, stopping at the first hit,
with the result and its origin stored on `companies.website_url`:

1. The catalogue's own `website_url`, once any source fills it.
2. Domains mentioned in the company's stored postings, excluding ATS, social,
   CDN, and job-board hosts; the most frequent remaining domain.
3. Wikidata: search the label, keep items typed as a business, require an
   exact label match, read P856. Measured on 2026-09-03: Datadog and Anthropic
   resolve; "Hudl" returns surnames, "Pinpoint" returns a Romanian consultancy,
   "WPP Media" nothing. Ambiguity resolves to nothing, not to a guess.

A company with no resolvable website is recorded as checked and not retried
every run. Its Pinpoint board, if any, stays `named`.

## Polling and lifecycle

Ingestion reads its boards from the registry and nothing else; the `boards`
key of `SKILLSYNC_SOURCE_CONFIG` goes away (`base_url` stays). After each
poll the row records the time, the posting count, and the failure streak.
Three consecutive fetch failures make a board `inactive`; it leaves the walk,
and because it is no longer in the walk the run can still be exhausted, so
the existing per-source reconciliation retires its provenance and withdraws
any job no other source lists. Rediscovery, or a later successful probe,
reactivates it.

Re-verification runs monthly through the same verification path. A board
that now states another company becomes `wrong_company` immediately and stops
being polled. Pinned rows are reported, never changed.

Operators keep a small script: `boards.py list | add | block | unblock`.
`add` pins; `block` is how a person overrules discovery.

## Policy

`docs/job-source-policy.md` treats career-page crawling as a separate,
undecided class. Website corroboration is not that: it reads at most three
pages of a company's own site to look for a link to its board, extracts no
postings, and obeys `robots.txt`. The policy gains a carve-out saying exactly
that, so the boundary stays written down.

## What does not change

Provider modules keep their shape; the contract gains one optional hook for
providers whose verification needs more than the feed (Pinpoint). The
canonical job contract, deduplication, matching, and reconciliation are
untouched. Arbeitnow is not a board provider and is not affected.

## Delivery

One issue and one pull request per row, in order:

| Issue | Change |
| --- | --- |
| #330 | `job_boards` table, model, migration, seeded pinned Greenhouse boards |
| #331 | ingestion polls the registry; env `boards` removed; operator script |
| #332 | poll lifecycle: failure streak, `inactive`, reactivation |
| #333 | discovery run for Greenhouse and Polymer: seeding, budget, cadence, persistence |
| #334 | company website resolution |
| #335 | Pinpoint verification: identity and website corroboration; policy carve-out |
| #336 | discovery DAGs in the factory |
| #337 | periodic re-verification and `wrong_company` demotion |

#330 through #333 deliver automatic Greenhouse and Polymer end to end.
#334 and #335 add Pinpoint. #336 schedules it. #337 keeps it honest.

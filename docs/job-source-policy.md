# Job source policy

Access terms and products change. Every source decision therefore records the
evidence and the date it was checked, and must be rechecked before implementation.

## The gate

Before writing an adapter, its issue must answer **yes** to all four questions:

1. **Documented access:** Is there an official, documented access path that the
   source permits SkillSync to use?
2. **Permitted retrieval:** Do the source's current terms allow automated
   retrieval and SkillSync's intended storage and display of the results?
3. **Stable schema:** Is the response schema documented and stable enough to
   validate at the source boundary?
4. **Stated rate limit:** Is the maximum request rate or request budget written
   down? Record the provider's published limit. If a public endpoint publishes
   no ceiling, state a conservative project limit instead and record that the
   provider limit is unpublished.

The review must link the official access documentation and terms, state the
answer to each question, and include an ISO check date. One "no" or an answer
that cannot be verified blocks the adapter. A previous decision is not evidence
that the current terms still allow it.

## Tier one — public board endpoints

Tier-one sources expose public job-board data in a documented JSON or similarly
structured feed. They fit the existing ingestion boundary: one client, one
source validator, and one normalizer. They do not need new orchestration.

The two built sources have this shape:

| Source | Access, terms, and schema | Rate limit | Checked |
| --- | --- | --- | --- |
| Arbeitnow | The [Job Board API](https://www.arbeitnow.com/blog/job-board-api) documents a keyless JSON API, and the [API terms](https://www.arbeitnow.com/terms#11-api) permit API use subject to attribution and revocation. The linked API documentation defines the response fields. | No provider ceiling is published. SkillSync's current ceiling is 20 pages per hourly run, with no overlapping runs and at most three transport attempts per page. | 2026-08-25 |
| Greenhouse | The [API overview](https://support.greenhouse.io/hc/en-us/articles/10568627186203-Greenhouse-API-overview) says the Job Board API exports public posts for programmatic retrieval and display; the [Job Board API reference](https://developers.greenhouse.io/job-board.html) defines the JSON endpoints and fields. | No provider ceiling is published. SkillSync makes one request per configured board per run, with at most three transport attempts. Greenhouse remains on demand; any schedule must state its maximum frequency first. | 2026-08-25 |

Two more tenant-board sources pass the gate and may be built on the shared
board framework:

| Source | Access, terms, and schema | Rate limit | Checked |
| --- | --- | --- | --- |
| Polymer | The [developer documentation](https://developer.polymer.co/) describes a keyless Public API that "provides unauthenticated access to job listings" and is "intended for job board integrations", which is SkillSync's use. The same page lists the job fields and the paging envelope. | The documentation says the endpoints are rate-limited and publishes no number. SkillSync makes one request per page per configured organisation per run, at most one hundred pages per organisation, with at most three transport attempts per request. | 2026-09-03 |
| Pinpoint | The [job feeds overview](https://developers.pinpointhq.com/docs/job-feeds-overview) says the feeds exist "to help display your jobs on another website", and the [listing guide](https://help.pinpoint.support/en/articles/5878344-how-to-list-pinpoint-jobs-on-any-website) names job boards as a consumer of the public RSS feed. The [postings JSON reference](https://developers.pinpointhq.com/docs/jobs-json-endpoint) lists every attribute. | No provider ceiling is published. SkillSync makes one request per configured subdomain per run, with at most three transport attempts. | 2026-09-03 |

Three remote-job aggregators pass the gate and run on the aggregator pattern.
SkillSync's own product already satisfies what each requires: every listing
links to the original posting and names its source.

| Source | Access, terms, and schema | Rate limit | Checked |
| --- | --- | --- | --- |
| Jobicy | The [API documentation](https://jobi.cy/apidocs) describes a keyless JSON endpoint (`/api/v2/remote-jobs`) and states that listings may be used in other products without individual permission, provided Jobicy is credited with a direct link and the canonical job URL is preserved. The same page lists every field. | Jobicy asks for polling at most once an hour and for responses to be cached. SkillSync makes one request per hourly run, with at most three transport attempts. | 2026-09-15 |
| Remotive | The [API documentation](https://remotive.com/api-documentation) and the legal notice embedded in every response permit sharing the jobs with a link back to the Remotive URL and a Remotive credit, forbid reposting to other job boards, and note that listings are delayed by a day. The response carries every field. | Remotive asks for at most four requests a day and blocks excessive traffic. SkillSync makes one request every six hours, with at most three transport attempts. | 2026-09-15 |
| Himalayas | The [API documentation](https://himalayas.app/api) describes a keyless JSON endpoint (`/jobs/api`) with cursor pagination, permits use with a link back and Himalayas credited as the source, and forbids reposting to other job boards. The documentation lists every field. | No numeric ceiling is published; the API answers excessive traffic with 429. SkillSync walks at most twenty-five pages of twenty every three hours, honours `Retry-After`, and makes at most three transport attempts per page. | 2026-09-15 |

The remaining tenant-board candidates were reviewed on the same date and did
not pass. Their entries are under blocked sources below, each with what would
change the answer. A blocked verification is not a prohibition: several of
these systems say nothing either way, and a written statement from the
provider would reopen the review.

## Tier two — licensed and keyed sources

Tier-two sources need a credential to call, and their terms go beyond
attribution: a trial period, a licence, a published call budget, or an
obligation to remove data on termination. They run on the same ingestion
boundary as tier one with two things the framework adds. Credentials are read
one environment variable each and never logged, and every call is reserved
against the source's daily quota before it is made, so a misconfigured
schedule cannot burn an account. The design is in
[the keyed sources spec](superpowers/specs/2026-09-15-keyed-sources-design.md).

| Source | Access, terms, and schema | Credential | Quota | Checked |
| --- | --- | --- | --- | --- |
| Adzuna | The [API documentation](https://developer.adzuna.com/overview) and the [interactive reference](https://developer.adzuna.com/activedocs) document `/v1/api/jobs/{country}/search/{page}` and its response fields. `description` is a snippet of the posting, so every record is stored with `partial_description` and is never merged with another source's posting by text. The [terms](https://developer.adzuna.com/docs/terms_of_service) say organisations are "subject to a 14 day trial period" and that "After the trial period ends, a licence agreement may be required"; they require "Label each displayed advert with 'Jobs by Adzuna'", which the listing must render before the source is enabled in production (#367); and termination requires removing acquired data. Trial start date: not yet started. | `SKILLSYNC_ADZUNA_APP_ID`, `SKILLSYNC_ADZUNA_APP_KEY` | Adzuna publishes "25 hits per minute, 250 hits per day, 1000 hits per week, 2500 hits per month". SkillSync reserves every call against 250 a day and schedules six runs of at most 36 calls, 216 a day, with at most three transport attempts per call that share one reservation. | 2026-09-15 |

## Blocked sources

### LinkedIn — blocked

**Checked 2026-08-25.** LinkedIn has no open API for retrieving job-search
results. Its [Job Posting API program](https://www.linkedin.com/legal/l/job-posting-api-terms)
is a vetted program for approved clients to manage postings, not an open search
feed. Its [crawling terms](https://www.linkedin.com/legal/crawling-terms) prohibit
automated crawling without express permission. There is therefore no permitted
access path, stable retrieval schema, or rate limit for SkillSync's use.

This answer changes only if LinkedIn provides and approves SkillSync for a
documented job-search API whose terms permit retrieval, storage, and display,
and publishes a stable schema and rate limit.

### Indeed — blocked

**Checked 2026-08-25.** Indeed's former Publisher Job Search API is not open to
new applicants. The current [job-posting integration guide](https://docs.indeed.com/job-postings/)
offers publishers a front-end JavaScript plugin; its APIs create or manage jobs
rather than provide an open job-search feed. The current
[API catalogue](https://docs.indeed.com/api-guides/) lists no replacement
job-search retrieval API. SkillSync therefore has no permitted access path,
stable search schema, or rate limit to build against.

This answer changes only if Indeed accepts new consumers into a documented
job-search API program and its terms permit SkillSync's retrieval, storage, and
display, with a stable schema and stated rate limit.

### SmartRecruiters — blocked

**Checked 2026-09-03.** The [Posting API](https://developers.smartrecruiters.com/docs/posting-api)
is documented and keyless for public postings, but `https://api.smartrecruiters.com/robots.txt`
disallows every path under `/v1/companies/` to all agents except LinkedIn's,
which is a machine-readable refusal of exactly the endpoint SkillSync would
poll. The [customer terms](https://www.smartrecruiters.com/legal/terms-and-conditions/)
do not address third-party retrieval, and the published
[10 requests per second](https://developers.smartrecruiters.com/docs/rate-limiting)
is not scoped to the public Posting API.

This answer changes only if the robots rules admit general agents on that path
or SmartRecruiters states in writing that third-party retrieval, storage, and
display of public postings is permitted.

### Recruitee — blocked

**Checked 2026-09-03.** The [Careers Site API](https://docs.recruitee.com/reference/intro-to-careers-site-api)
is keyless and documented, but the Recruitee API Terms and Conditions
(v2022.1.0, clause 2.6.5) prohibit copying, scraping, or exporting data in
bulk from the service, which describes ingestion. The terms are linked from
`https://recruitee.com/forms/api-terms`, which did not resolve on the check
date; the document itself was retrieved from Recruitee's file host. The
[offers reference](https://docs.recruitee.com/reference/offers-get) lists
parameters but not the response fields.

This answer changes only if the API terms are revised or Recruitee grants
written permission for this use.

### Lever — blocked pending verification

**Checked 2026-09-03.** The [Postings API](https://github.com/lever/postings-api)
is keyless, documents its fields, and says it is "designed to help you create a
job site". It notes that published postings "may be scraped by third parties",
which is an observation about visibility rather than a grant of permission,
and the [terms of service](https://www.lever.co/legal/terms-of-service) do not
address third-party retrieval. No read-side rate limit is published; the only
number, two requests per second, applies to application submissions.

This answer changes only if Lever's documentation or terms state that third
parties may retrieve, store, and display public postings.

### Ashby — blocked pending verification

**Checked 2026-09-03.** The [Public Job Posting API](https://developers.ashbyhq.com/docs/public-job-posting-api)
is keyless and documents its fields, but frames its use as "if you host your
own careers page, you can use this data to populate it". The
[terms](https://www.ashbyhq.com/resources/terms) bind customers and say
nothing about third-party consumers. No rate limit is published.

This answer changes only if Ashby states that job boards or aggregators may
consume the endpoint.

### Workable — blocked pending verification

**Checked 2026-09-03.** The [public jobs endpoint](https://workable.readme.io/reference/jobs-1)
is keyless and documents its schema, but neither it nor the
[terms](https://www.workable.com/terms) say who may consume it. No rate limit
is published for it.

This answer changes only if Workable's documentation or terms address
third-party retrieval and display.

### Personio — blocked pending verification

**Checked 2026-09-03.** The [XML feed](https://developer.personio.de/docs/retrieving-open-job-positions)
is keyless and documents its fields, but the page does not say who may consume
it, and Personio's terms page could not be retrieved on the check date. No rate
limit is published.

This answer changes only if the terms can be read and permit this use, or
Personio states that the feed is intended for job boards.

### JazzHR — blocked

**Checked 2026-09-03.** No documented public access path exists. The XML feed
URL is issued inside each customer's account settings and described as scoped
to that account's key, and the REST API is likewise per customer. The terms of
service could not be retrieved on the check date.

This answer changes only if JazzHR publishes a documented public feed with a
constructible URL and terms that permit third-party retrieval.

### Talexio — blocked

**Checked 2026-09-03.** No public developer documentation describes a job
postings API. An endpoint can be observed on a live careers site, and one site
can host several employers, so nothing documented ties a subdomain to a
company. The [site disclaimer](https://talexio.com/disclaimer/) addresses only
website content.

This answer changes only if Talexio publishes documentation and terms for a
public postings endpoint.

## Separate class — company career-page crawlers

A company career page is not a tier-one source. It is per-site HTML whose markup
can change without a schema version or error response. Supporting crawlers would
need a separate decision covering at least:

- each site's `robots.txt` and terms;
- ownership and maintenance for every site-specific parser; and
- detection of silent breakage, including stale-success and unexpected-count
  monitoring.

That decision is **undecided**. This policy neither approves crawling nor chooses
its design, and no crawler should be implemented as a tier-one adapter.

### Verification fetches are not crawling

**Added 2026-09-14.** Automatic board registration for a provider whose feed
states no company (Pinpoint) may verify a guessed board by fetching, per
company: a careers site's front page and its RSS feed, and at most three
pages of the company's own website. The same three pages may also be read to
learn which board a site links to, when no guessed board answered at all; no
new pages are fetched for this. When a page links several boards, each is
asked for its board feed, at most five per page, which is a board request
rather than a website page, so the three-page limit is unchanged; a page
linking more than five is treated as a directory and none is asked. Nothing
here extracts postings; the only question ever asked of a page is whether it
names or links a board this already suspects exists. Every website fetch
obeys `robots.txt` and identifies itself by user agent.

That is not the career-page crawling this section leaves undecided. A
crawler reads a site's markup to extract postings, on an ongoing basis, for
sites this policy has not looked at. Verification reads at most three pages
once per company, per recheck cycle, never for postings, and only to
corroborate a guess this system already made from other evidence. See
`docs/superpowers/specs/2026-09-03-automatic-board-registry-design.md` for
the design this carve-out belongs to.

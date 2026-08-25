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

Other systems with the same likely adapter shape include
[Lever](https://github.com/lever/postings-api),
[Ashby](https://developers.ashbyhq.com/docs/public-job-posting-api),
[Workable](https://www.workable.com/developers),
[Recruitee](https://support.recruitee.com/en/articles/1066282-api-documentation),
[SmartRecruiters](https://developers.smartrecruiters.com/docs/posting-api), and
[Personio](https://developer.personio.de/docs/retrieving-open-job-positions).
This is a candidate list, not approval: each source still needs its own dated
four-part gate review before an adapter is written.

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

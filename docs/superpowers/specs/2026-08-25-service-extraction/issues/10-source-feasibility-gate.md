# 10 — A feasibility gate for job sources

## Why
The intended source list mixes two very different things. Arbeitnow and
Greenhouse are public JSON board endpoints, and the existing adapter pattern
handles them with a client, a validator, and a normalizer. LinkedIn has no open
job-search API and scraping it is against its terms. Indeed's publisher search
API is not open to new applicants. Company career pages are per-site HTML
crawlers, which fail silently on markup changes and need per-site upkeep.

Without a written gate, each of these gets re-argued whenever the source list
comes up.

## Scope
Add `docs/job-source-policy.md`:

- **The gate.** Before an adapter is written, a source must have: a documented
  and permitted access path, terms that allow automated retrieval, a stable
  response schema, and a stated rate limit. Record the answer for each, with
  the date checked and a link — access terms change, and a decision without a
  date cannot be rechecked.
- **Tier one — same shape as today.** Public board endpoints: Arbeitnow (built),
  Greenhouse (built), and candidates such as Lever, Ashby, Workable, Recruitee,
  SmartRecruiters, Personio. A new one costs a client, a validator, and a
  normalizer, and no new orchestration.
- **Blocked, with the reason stated.** LinkedIn and Indeed, each with what
  would have to change for the answer to change.
- **Crawlers are a separate class.** Company career pages are not a source in
  the tier-one sense. They need their own decision covering robots.txt, per-site
  maintenance, and how silent breakage is detected. Do not decide it here;
  record that it is undecided.

## Out of scope
Writing any adapter. Deciding the crawler question.

## Acceptance
- The document states the gate, the tiers, and each blocked source's reason and
  check date.
- `docs/delivery-plan.md` links to it from wherever sources are discussed.

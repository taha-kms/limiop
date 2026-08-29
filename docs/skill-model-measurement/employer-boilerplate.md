# Employer boilerplate, measured — 2026-08-29

Issue #245. #201 removed the aggregator's own footer and deliberately left
employer boilerplate alone, because the blocks in question are prose an employer
chose to write. The candidate generator then made the cost visible: of twenty
observations read by hand, six came from one employer's blurb about itself.

## The rule

A block is removed when all three hold:

1. its employer has at least **5 postings** in the run, so there is a pattern
   rather than a coincidence;
2. the block appears in at least **60%** of that employer's postings;
3. the block **names the employer**.

The third condition is the one doing the work. Repetition alone does not
establish that a block says nothing about the role — an employer whose postings
share a real requirement repeats that too. A block that names the employer is
the employer talking about itself; a requirement talks about the role.

The name is matched as a whole word, using the first token of the employer's
name that is neither a legal form nor shorter than four characters. Not every
token: `Quantum-Systems GmbH` would otherwise own every repeated sentence about
distributed systems, and `Allica Bank` every sentence about banks.

Both halves are derived from the postings. A per-employer list of paragraphs
would rot the moment the employer edited their template.

## What it drops

Over the stored catalogue — 1,422 postings, 477 employers, 25 of them with at
least five postings — the rule drops **51 blocks across 18 employers** and
changes **661 postings**. Every block in the drop set was read by hand. They are
mission statements, benefits lists, legal and anti-scam notices, diversity
statements, and section headings that name the employer. None states a
requirement.

For the employer that prompted the issue, all six of its blocks go:

| Block | In |
| --- | ---: |
| `About Anthropic` | 536/536 |
| `Anthropic's mission is to create reliable, interpretable, and steerable AI systems…` | 536/536 |
| `We believe that the highest-impact AI research will be big science. At Anthropic…` | 536/536 |
| `The easiest way to understand our research directions… prior to Anthropic, including: GPT-3…` | 536/536 |
| `Anthropic is a public benefit corporation headquartered in San Francisco…` | 536/536 |
| `Your safety matters to us… Anthropic recruiters only contact you from @anthropic.com…` | 536/536 |

What survives in the same postings is the point of the third condition:

- `Working fluency with data, including SQL` — in all 536, kept.
- `Minimum education: Bachelor's degree or an equivalent combination…` — kept.
- `Minimum years of experience: Years of experience required will correlate…` — kept.
- `Location-based hybrid policy: Currently, we expect all staff to be in one of our offices at least 25% of the time.` — kept.

A rule keyed on repetition alone would have taken all four, SQL included.

## Before and after

Counted with `scripts/measure_boilerplate.py`, which applies the rule to the
stored descriptions and runs the candidate generator over both versions. These
are the generator's **proposals**; the stored inbox holds only what the
vocabulary could not resolve, so it is a subset. Both columns are the same
quantity, which is what makes them comparable.

| | Before | After | Change |
| --- | ---: | ---: | ---: |
| Observations proposed | 104,352 | 77,906 | **−25.3%** |
| Distinct terms | 16,541 | 16,490 | −0.3% |
| Description characters | 8,460,046 | 7,188,700 | −15.0% |

The two rows say different things and both are worth reading. A quarter of
everything the generator proposes came from text no employer wrote about a role.
The vocabulary of the inbox barely moves, because boilerplate repeats the same
few terms thousands of times: this removes volume, not variety — and volume is
what a reviewer reads through.

## The terms the issue named

`mentions` is occurrences; `employers` is distinct companies, which is how the
review queue ranks. The stored column is `job_skill_mentions` as it stands
today, for context.

| Term | Stored inbox | Proposed before | Proposed after |
| --- | ---: | ---: | ---: |
| `San` | 289 / 8 employers | 608 / 15 | **72 / 15** |
| `Safety` | 288 / 3 | 599 / 6 | **63 / 6** |
| `About Anthropic Anthropic` | 256 / 1 | 545 / 1 | **0 / 0** |
| `Neurons` | 251 / 1 | 538 / 1 | **2 / 1** |
| `Concrete` | 250 / 1 | 536 / 1 | **0 / 0** |
| `anthropic.com/careers` | 250 / 1 | 536 / 1 | **0 / 0** |

`San` and `Safety` survive at a tenth of their volume because other employers
use them in prose of their own, which is the correct outcome: the rule removes
one employer's blurb, not a word from the language.

## What this does not do

- **Nothing already stored changes.** The rule runs before a description is
  stored, so the 536 postings above keep their boilerplate until they are
  ingested again. The "after" column is what the next run produces, not the
  state of the catalogue.
- **Employers are grouped per run.** An employer whose postings arrive a few at
  a time — most Arbeitnow employers — stays below the five-posting minimum and
  is left alone. That is the honest reading of having too little to establish a
  pattern, and it means the measured reduction above is an upper bound for
  sources that do not deliver an employer's board in one go.
- **A heading that names the employer goes with the blurb.** `WHAT YOU'LL BRING
  TO FLOCK:` is dropped while the requirements under it stay. The description
  loses a signpost and keeps its content.

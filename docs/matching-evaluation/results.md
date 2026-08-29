# The skill-overlap baseline, measured — 2026-08-29

The gate every later matcher has to beat. Issue #214.

| Metric | Value |
| --- | ---: |
| NDCG@5 | **0.8055** |
| Precision@1 | **0.8333** |
| Explanations shown | 28 |
| Mean skills per explanation | 3.32 |
| Share naming a matched skill | 1.0 |

Corpus version 1, alias table `2026.08.29.1`,
6 candidates and 12 postings.

## Per candidate

| Candidate | NDCG@5 | P@1 | Top result | Its grade | Matched |
| --- | ---: | ---: | --- | ---: | ---: |
| `backend-generalist` | 0.9155 | 1 | `backend-engineer` | 2 | 4/4 |
| `ml-practitioner` | 1.0 | 1 | `ml-engineer` | 2 | 4/4 |
| `analyst` | 0.9816 | 1 | `data-analyst` | 2 | 3/3 |
| `designer` | 1.0 | 1 | `product-designer` | 2 | 3/3 |
| `seller` | 0.936 | 1 | `account-executive` | 2 | 3/3 |
| `newcomer` | 0.0 | 0 | `account-executive` | 0 | 1/3 |

## What the corpus is

Synthetic, hand-graded, and committed at [`corpus.json`](corpus.json). Six
candidates and twelve postings, built from concepts the shipped alias table
actually publishes, so every grade can be checked by reading the two skill
lists rather than by trusting this document.

Relevance is graded 2 for the role the candidate is for, 1 for a role they
could plausibly take, and 0 for the rest. The grades were assigned by reading
the skill sets, never by running the matcher — a corpus graded by the thing it
scores measures nothing.

## What the metrics mean

**Ranking** is NDCG@5 over those grades, plus precision@1: whether the first
posting shown was one the candidate should see at all.

**Explanation** is not scored for correctness, because correctness is exact by
construction — the corpus states both skill sets, so matched and missing are
arithmetic. What is worth measuring is whether an explanation is usable. A
result naming one matched skill and thirty missing ones is complete and tells a
candidate nothing, so the reported figures are how many skills a shown
explanation carries and how often it names at least one the candidate already
has.

## What it cannot tell you

**It is not real candidates.** Nobody has that data, and inventing plausible
CVs would produce a corpus confident about a population it never saw. What a
synthetic corpus can do is be small enough to argue with, which is worth more
here than being large.

**It says nothing about the catalogue.** Every posting in it carries extracted
skills. About two thirds of the 1,252 stored postings carry none, and against
those the baseline scores zero by design. This measures the ranking, not the
reach of the vocabulary, and those are different problems.

**Twelve postings is not a ranking benchmark.** NDCG@5 over twelve candidates
per query is a sanity check with a number attached. It will catch a matcher
that ranks backwards. It will not separate two good matchers, and #218 should
not be adopted on a difference this corpus is too small to resolve.

## The finding

**A candidate with one generic skill gets a confident ranking that means
nothing.** `newcomer` holds a single concept — Communication skills — and the
baseline duly returns `account-executive` at 0.33, having matched one skill of
three. Nothing is wrong with the arithmetic. The result is useless, and it
looks exactly like a useful one.

That is a product decision, and it belongs in the matching endpoint rather than
here. `matching_ready()` already exists with
`PROVISIONAL_MINIMUM_USABLE_SKILLS = 1`, which the design spec calls a formality
rather than a threshold and which has no production caller. One skill is not
enough to rank a person, and this is the measurement that says so.

That single zero is also the whole gap between the reported 0.8055 and the
0.9666 the other five candidates average. The mean including the case the
product should refuse to answer is the honest figure to beat, so it is the one
reported.

## Reproducing

```bash
cd backend && python scripts/evaluate_matching.py
```

The headline numbers are asserted by a test, so a change to the matcher that
moves them fails rather than quietly rewriting the gate.

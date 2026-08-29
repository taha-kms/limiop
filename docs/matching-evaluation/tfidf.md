# TF-IDF against the baseline — 2026-08-29

Issue #218. Evaluation only: nothing serves TF-IDF, and adopting it would be a
separate change with its own review.

## Recommendation

**Keep the skill-overlap baseline.** TF-IDF gains 0.0101 NDCG@5 on a corpus this
document's own predecessor declared too small to resolve a difference that size,
and it costs the agreement between the score and the explanation — which is what
this product is actually promising.

## The numbers

Same corpus, same metrics, same command.

| | Skill overlap | TF-IDF cosine |
| --- | ---: | ---: |
| NDCG@5 | 0.8055 | **0.8156** |
| Precision@1 | 0.8333 | 0.8333 |
| Explanations shown | 28 | 28 |
| Mean skills per explanation | 3.32 | 3.32 |
| Share naming a matched skill | 1.0 | 1.0 |
| Latency, full evaluation | 0.271 ms | 0.471 ms |

Per candidate, TF-IDF moves two of six and changes nothing else:

| Candidate | Overlap | TF-IDF |
| --- | ---: | ---: |
| `backend-generalist` | 0.9155 | 0.9155 |
| `ml-practitioner` | 1.0 | 1.0 |
| `analyst` | 0.9816 | **1.0** |
| `designer` | 1.0 | 1.0 |
| `seller` | 0.936 | **0.9779** |
| `newcomer` | 0.0 | 0.0 |

## What was measured

Each posting is a document whose terms are its required concepts; the candidate
is a query of the concepts they hold. Term frequency is binary — a posting
asking for Python twice does not ask for it twice — so all the weighting comes
from inverse document frequency, which is the claim being tested: that a
concept few postings ask for should count for more than one nearly all of them
ask for. Similarity is cosine between the weighted vectors.

Only the score is replaced. Matched and missing concepts are computed
identically, so the two rankings are comparable on the one thing that differs.

## Why the quality difference does not decide it

0.0101 NDCG@5 across six candidates and twelve postings is two candidates
moving. The baseline's own write-up said this before there was anything to
compare: *"Twelve postings will catch a matcher that ranks backwards. It will
not separate two good matchers, and #218 should not be adopted on a difference
this corpus is too small to resolve."* That was written without knowing which
way the difference would fall, and it applies.

Precision@1 is identical. Both matchers put the right posting first for the same
five candidates and refuse the sixth.

## Why latency does not decide it either

0.271 ms against 0.471 ms for the whole evaluation. TF-IDF is 1.7× the work and
both are far below anything a request would notice, because the corpus is small
either way. Latency would only become an argument at a catalogue size neither
number here predicts.

## What does decide it

**The score and the explanation stop agreeing.**

The `seller` candidate holds every skill `account-executive` asks for. Under
both matchers the page would show *"3 of 3 skills"*, with all three named and
nothing missing. The score beneath it:

| Matcher | Score shown | Explanation shown |
| --- | ---: | --- |
| Skill overlap | **1.00** | 3 of 3 skills, none missing |
| TF-IDF cosine | **0.84** | 3 of 3 skills, none missing |

There is no reading of the explanation that produces 0.84. Cosine normalises by
the candidate's own vector, so holding a skill the posting did not ask for
lowers the number — which is the asymmetry the baseline exists to refuse, and it
reappears here as a number the candidate cannot check.

The product promises matched and missing skills, not a similarity. A score
nobody can read back to the list beside it is a different product, and a worse
one to argue with. That is the trade-off, and it is not worth 0.0101.

## When to revisit

Not on this corpus. TF-IDF becomes worth re-measuring when there is a corpus
large enough to resolve a difference this size, and when there is an answer to
what a cosine score means to a reader looking at the skills behind it. Neither
exists yet, and inventing either to justify the adoption would be fitting.

## Reproducing

```bash
cd backend
python scripts/evaluate_matching.py --matcher "skill-overlap baseline"
python scripts/evaluate_matching.py --matcher "tf-idf cosine"
```

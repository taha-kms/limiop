# Embeddings against the approved matcher — 2026-08-29

Issue #63. Evaluation only. Nothing here entered production, and the conclusion
is that nothing should.

## Recommendation

**Reject.** Embeddings score below both matchers already measured, cost 5.1 GB
of runtime to install, and produce a number with no explanation behind it.

| | NDCG@5 | Precision@1 |
| --- | ---: | ---: |
| Skill overlap (approved baseline) | **0.8055** | 0.8333 |
| TF-IDF cosine (#218, rejected) | 0.8156 | 0.8333 |
| Sentence embeddings | **0.7896** | 0.8333 |

Same corpus, same metrics, same cutoff. Precision@1 is identical across all
three: every matcher puts the right posting first for the same five candidates
and refuses the sixth.

## What was measured

Model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`,
sentence-transformers 6.0.0 on torch 2.13.0. Multilingual, which the delivery
plan's skill-model decision specifically called for — about a quarter of the
stored catalogue is German.

Each concept label is encoded, a candidate and a posting are each represented by
the mean of their concepts' vectors, and similarity is cosine between the two.
Encoding the *labels* rather than the posting text is deliberate: it is the
comparison the corpus supports, and it tests the actual claim — that semantic
nearness between skill names beats exact set overlap.

## Cost

| | |
| --- | ---: |
| Runtime install (torch, transformers, dependencies) | 5.1 GB |
| Model weights | 458 MB |
| Model load, per process | 4.84 s |
| Encoding 26 labels | 0.154 s |
| Ranking 12 postings, once loaded | 0.059 ms |

Ranking is fast once the model is in memory, which is the argument for
precomputing vectors at ingestion (#131). The cost that does not go away is the
5.1 GB and the 4.84 seconds every process pays before it can answer anything.

## Why it loses

**It scores partial credit for being nearby, and nearness is not the question.**
The `seller` candidate drops from 0.936 under the baseline to 0.8403 here,
because a recruiter's skills sit close to a seller's in the embedding space and
the model has no way to know the candidate lacks them.

**It makes a meaningless profile look confident.** `newcomer` holds one generic
concept. The baseline offers it a 0.33 match, which is at least visibly weak.
Embeddings offer `technical-recruiter` at **0.77** — a strong-looking score for
a candidate the product refuses to rank at all. A wrong answer that looks
confident is the failure mode this repository has now hit twice, and the encoder
makes it worse rather than better.

**It has no explanation.** Cosine over centroids produces a number and nothing
else. The product promises matched and missing skills, and a score nobody can
read back to a list is a different product — the same objection that decided
#218, except TF-IDF at least kept the sets alongside its number.

## What this means for #131

`#131` asked for job embeddings precomputed during ingestion, with a stored
model version and a resumable re-embedding job. It was scoped on the assumption
that embeddings would be adopted. They are not, so there is nothing to
precompute: storing a vector per posting, versioning it, keeping it in step with
withdrawal and re-appearance, and migrating the whole catalogue when the model
changes are all real costs, and every one of them buys a matcher that scores
worse than the one already shipped.

The interactions #131 named are still correctly identified. If a future
evaluation on a corpus large enough to resolve the difference reverses this,
that issue is the right design to build from.

## The threshold this was judged against

Adoption required a measured improvement over the approved baseline. It scored
**0.0159 NDCG@5 below** it. There is no reading of these numbers under which the
cost is bought.

## Reproducing

The evaluation is not committed as a runnable script, and that is deliberate: it
would add torch to a repository whose backend image is deliberately small, to
run a comparison whose answer is recorded here. The method is stated above in
enough detail to rebuild in an hour, and the corpus and metrics it used are
committed.

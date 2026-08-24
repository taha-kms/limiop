# The skill model — decision

Approved 2026-08-24. This is the Phase B exit: the spec that exists before any
skill table does.

Evidence: `../../skill-model-measurement/results.md`, measured against a gold
set frozen at commit `868bc12` before any candidate vocabulary was built.

## The decision

SkillSync uses a **hybrid skill representation**. Not ESCO alone, not a curated
list alone, and not unrestricted free text.

- **Known skills normalize to canonical concepts.** One concept, many surface
  forms, so `product demos` and `product demonstration` become the same thing.
- **ESCO is an optional mapping layer**, applied where the mapping is
  confident, and absent where it is not. It is not the vocabulary.
- **Legitimate unknown skills are preserved** rather than discarded.

Matching combines **pretrained multilingual semantic embeddings** with
**explicit skill overlap** and **structured profile signals**. Job embeddings
are precomputed during ingestion; candidate embeddings are generated from the
canonical candidate profile. The first version uses a measurable baseline
rather than a trained model.

## Why, from the measurement

Each single-vocabulary option failed differently, and the failures are what
force a hybrid.

| arm | recall | precision |
| --- | --- | --- |
| free text, 77,407 terms | 0.974 | 0.151 |
| curated list, 184 forms | 0.412 | 0.227 |
| ESCO, 65,850 labels | 0.285 | 0.233 |

Free text's recall is saturation: it matched 20,563 spans against 2,059 gold
mentions, so it finds almost everything by finding almost everything. It cannot
rank. The two disciplined arms miss more than half.

184 hand-written surface forms beat 65,850 ESCO labels on recall by 12.7
points, interval [0.095, 0.160]. Vocabulary size did not predict coverage.
ESCO's labels are written in ESCO's register and job postings are not, which is
exactly why ESCO belongs as a mapping layer rather than as the vocabulary.

Two careful annotators, working from one frozen guide with no vocabulary in
view, gave the same span different names 36.7% of the time. That is the case
for canonical concepts stated as a measurement rather than as a preference: if
people cannot converge on names unaided, extracted names will not join across a
CV and a job.

The tail no arm found was 28 named products and standards out of 38 — `QGIS`,
`Sage 200`, `NIST`, `CSPM`, `tapeout`, `nue.io`. New ones arrive faster than
any list is curated, which is the case for preserving unknowns and for a
semantic layer that does not depend on having seen the string before.

## What this obliges, and what it still leaves open

Four consequences worth naming now rather than discovering later.

### The "legitimate" in legitimate unknown skills is load-bearing

Unrestricted free text was 85% junk. Preserving unknowns re-admits exactly that
population unless something decides which unknowns are real. That gate is the
difference between this design and the arm the measurement rejected, and it is
not yet specified. It needs its own rule and its own evaluation before unknowns
are stored.

### Embeddings in v1 changes a settled decision

The delivery plan settled: skill overlap, then TF-IDF, then embeddings, each
evaluated before adoption. #49, #53, and #63 are sequenced on that ladder.
Combining embeddings with overlap in the first version steps over the middle of
it.

The recommendation is to keep the ladder's purpose while accepting the
decision: **skill overlap alone remains the measured baseline, and the hybrid
ships only if it beats that baseline on a held-out set.** Pretrained weights
with a pinned version are a baseline rather than a trained model, which is what
the decision asks for, but "measurable" has to mean something was measured.

### Multilingual embeddings may reopen the German share

The measurement fixed English-only for v1 and reported the cost: 26.95% of the
catalogue is not English, 867 German postings out of 3,354. A multilingual
encoder does not need that exclusion. Whether v1 now serves German is a
scope decision that this choice makes available and does not itself make.

### Precomputed embeddings need a version and a way to be rebuilt

Embedding at ingestion means the stored vector belongs to a model version. That
version has to be recorded per row, changing it has to be a migration rather
than a surprise, and #47 and #48's requirement that extraction be deterministic
and versioned applies to the encoder too. Lifecycle interacts: a job withdrawn
under #94 keeps its vector until it is removed, and re-embedding the catalogue
must be a bounded, resumable job rather than an outage.

## What this reshapes

- **#46** stops being "add deterministic skill normalization" against an
  unnamed vocabulary. It becomes the canonical-concept model: concepts,
  surface forms, the alias table, and the unknown-skill gate.
- **#47 and #48** keep their determinism and evidence requirements and gain the
  encoder as a versioned artifact.
- **#49** remains the baseline the hybrid must beat, rather than the shipped
  matcher.
- **#53 and #63** are reshaped by embeddings arriving earlier than planned.
- A new issue is needed for job-embedding precomputation in the ingestion
  pipeline, and another for the unknown-skill gate.

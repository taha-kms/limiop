# Measuring the unknown-skill admission gate — #130 methodology

This is the measurement and annotation plan for #130. It is deliberately not
an implementation of the gate. The acceptance criteria require precision and
recall against held-out annotated data, and no eligible held-out positive set
exists yet.

The 80-posting Phase B gold set was first frozen at `868bc12` and contains
2,059 mentions over 78 postings. The same gold-set blob is carried in the
current history by `d505459`. All 80 postings were then used to score all three
Phase B arms. More importantly, #130 and the Phase B decision already name the
positive tail the gate is meant to preserve: `QGIS`, `Sage 200`, `NIST`,
`CSPM`, `SNMP`, `tapeout`, `nue.io`, `LucaNet`, and the other named products
and standards among the 38 misses. A rule built with those examples in view and
scored on those postings would be hand-fit to its test set.

The old set still has one valid use. The rejected free-text arm emitted 20,563
matched spans against 2,059 gold mentions at 0.151 strict precision. Its
non-gold candidates are rich in boilerplate, legal text, and job duties. They
are useful development negatives once blindly annotated; they are not fresh
positives and they are not the final score.

This plan freezes new data before a rule is chosen, just as
[the Phase B methodology](2026-08-23-skill-model-measurement-design.md) froze
its gold set before building an arm.

## What is being decided

The gate receives a candidate span that the frozen canonical vocabulary from
#46 did not resolve. It returns one of two decisions:

- `admit_unknown`: preserve the candidate with its evidence and versions.
- `reject`: do not store it as a skill.

The scoring unit is one `(posting, normalized candidate, evidence span)` tuple.
Repeated occurrences of the same candidate in one posting count once, using
the first accepted evidence span. The unit is deliberately not a bare string:
the same words can name a skill in a requirements section and be prose in a
legal footer.

A **legitimate unknown** satisfies all three conditions:

1. The span affirmatively associates a skill, tool, product, standard, method,
   domain, language, or working capability with doing the job under the
   existing annotation guide.
2. The frozen #46 resolver cannot map it deterministically to a canonical
   concept or alias.
3. It is specific enough to compare between a candidate profile and a job. A
   duty, qualification, benefit, legal category, or copied boilerplate is not.

This definition does not require capitalization, recurrence, a particular
posting section, or use by multiple employers. Those are candidate signals to
measure. Putting them in the annotation definition would make the experiment
confirm its own assumptions.

## The evidence has three roles

| evidence | allowed use | forbidden use |
| --- | --- | --- |
| Phase B missed tail and the examples in #130 | Understand the failure and design annotation examples | Final precision, recall, threshold selection, or regression claims |
| Phase B free-text candidates | Develop negative categories and screen candidate signals after blind judgement | Fresh-positive recall or the final score |
| New corpus, split by employer before annotation | Calibration and one sealed final evaluation | Retuning after the final holdout is opened |

The old gold annotations are not exhaustive enough to declare every
non-overlapping free-text match false. Phase B explicitly did not run its blind
false-positive pass. Candidates sampled from that pool therefore receive a new
blind `legitimate unknown` / `known skill` / `not a skill` judgement before
they are used, rather than inheriting a negative label from absence.

That pool is usable only if the Phase B descriptions can be reacquired
byte-for-byte against their frozen hashes and the frozen free-text arm can be
rerun. If they cannot, the historical negative pass is skipped and the fresh
development split supplies the negatives. Missing scratch data is not a reason
to relabel offsets against changed prose.

## Prerequisite: freeze what “unknown” means

#46 must land first. Its canonical concepts, surface forms, ambiguous-term
behaviour, and resolver version define whether a mention is known or unknown.
The following are frozen together before annotation starts:

- canonical vocabulary and resolver version;
- candidate-proposal extractor and version;
- normalization applied before candidate deduplication;
- unknown-annotation guide;
- corpus manifest, sample identifiers, split assignment, and seeds.

Changing the vocabulary changes the gold labels. Changing the proposer changes
which false positives can reach the gate. Either change starts a new
measurement version; neither is patched into an evaluation already under way.

## Fresh corpus

The fresh corpus must not contain the postings that produced the named missed
tail. It is a forward time slice collected after the Phase B snapshot, whose
latest `published_at` was `2026-08-23T19:30:29+00:00` and whose snapshot time
was `2026-08-23T20:09:00.702068+00:00`.

A posting is eligible only when all of the following hold:

- it is detected as English under the pinned detector;
- its `published_at` is later than the Phase B snapshot time;
- its source key and description hash do not occur in the Phase B sample;
- it comes from a successful, source-exhausted collection run;
- its description hash is unique in the new frame.

The frame is not frozen until it has at least 3,000 eligible postings. It must
include both production sources and at least 20 Greenhouse boards not among the
15 Phase B boards. No one employer may supply more than 5% of the frame. Counts
by source, board, employer, sector, and publication week go in the manifest.

The publication cutoff is the mechanical independence guarantee. New boards
and the employer cap reduce a second risk: carrying the same templates and
company-specific vocabulary into the new evaluation. If the frame cannot meet
these conditions, the result is blocked or explicitly limited; old Phase B
postings are not substituted to make the sample large enough.

No description text is committed. The manifest carries identifiers, hashes,
counts, and the cutoff. Annotation artifacts carry offsets, hashes, and
annotator-authored labels under the existing four-word and 64-character cap.

## Split before anyone annotates

Employers, not postings, are assigned to splits under a fixed seed. This keeps
one employer's footer and repeated job template from appearing on both sides of
a decision.

| split | share of eligible employers | use |
| --- | ---: | --- |
| development | 50% | Explore signal behaviour and draft interpretable rules |
| calibration | 25% | Select thresholds and choose one final rule |
| final holdout | 25% | One score only, after the rule version is frozen |

Assignment is stratified by source and sector, then checked against posting
counts. An employer stays in one split even when it appears through both
sources. The split manifest and seed are committed before annotation.

The final-holdout descriptions and annotations remain unavailable to the rule
author. A separate annotator or custodian holds them until the selected rule,
feature definitions, thresholds, and scoring script have been committed. The
holdout is not a third opportunity to improve the rule.

## What must be annotated, and how much

The primary positive sample is legitimate unknowns in randomly ordered whole
postings, not a list of terms selected for looking name-like. Each split is
annotated in fixed batches of 25 postings until it contains at least 100
adjudicated legitimate-unknown posting-and-skill pairs, then the current batch
is completed. Development, calibration, and final holdout each need 100 fresh
positives, so the minimum fresh-positive target is **300**.

The stop condition depends only on the number of gold positives, never on a
candidate rule's score. Each split has a hard cap of 400 postings. If any split
reaches the cap without 100 positives, its interval is reported as
underpowered and no gate is approved from that run.

The target follows the only observed rate available without touching new
labels. Phase B found 28 named product or standard misses in 78 postings, about
0.36 per posting. At that rate, 100 positives require about 278 postings and
the three splits require about 834. A design effect near Phase B's value of two
leaves roughly 50 independent-positive equivalents per split, enough to detect
only fairly large errors; the interval, not the target count, remains the
authority.

No quota forces the fresh positives to resemble the old named tail. The report
shows category, token length, singleton versus repeated use, source, sector,
and name-shape distributions. If the new sample contains few named products or
standards, that is a population finding, not a reason to insert the old 28.

### Negative coverage

Before the final evaluation, draw and blindly judge 600 candidates from the
old free-text pool for development: 150 each from apparent boilerplate, legal
text, job duties, and an unstratified remainder. The apparent category is
derived from position or section metadata and hidden from the annotator. These
labels help define failure slices; they do not enter the final metric.

On calibration, pool admissions that do not overlap a gold positive across all
candidate rules, strip rule and signal provenance, and sample up to 200 unique
candidates per rule. Shared candidates are judged once and rejoined to every
rule afterwards. On the fresh holdout, apply the same process to a random
sample of up to 400 non-overlapping final-rule admissions. Boilerplate, legal
text, and job-duty candidates are oversampled to at least 100 each when
available. Inclusion probabilities are retained so precision can be weighted
back to each split's population. Slice results are reported unweighted.

## Annotation protocol

An unknown-specific supplement to
[the existing guide](../../skill-model-measurement/annotation-guide.md) is
written and frozen before the first fresh posting is read. It adds examples of
the three-way boundary:

- a legitimate unknown skill;
- a known skill or alias, which is real but belongs to #46;
- text that is not a skill.

It does not reproduce the Phase B tail or issue examples. It includes invented
examples of products, standards, duties, qualifications, legal language, and
employer-owned products so annotators can apply the boundary without learning
the test answers.

Two annotators independently read every sampled posting. They see the frozen
guide and vocabulary version, but no candidate signal values, gate output,
other annotator output, old tail list, or split-level score. In this exhaustive
positive pass they record every skill mention that the frozen resolver does not
map, and skip mentions it resolves as known. For each recorded mention they
capture:

- posting key and description hash;
- canonical label, offsets, ESCO sub-pillar, and requirement flag;
- the resolver version and its unresolved result.

The separate candidate-judgement pass uses the three labels
`legitimate_unknown`, `known`, and `not_skill`. A `known` judgement records the
canonical concept identifier. A `not_skill` judgement records a short reason
code, including `boilerplate`, `legal`, `duty`, `qualification`, `benefit`, and
`other`. Annotators do not mark arbitrary non-skill spans during the exhaustive
positive pass.

Label-exact set F1, label-agnostic span-overlap F1, and category agreement are
reported. If span-overlap F1 for legitimate unknowns is below 0.70, the guide
is revised and both passes are rerun; adjudication does not conceal a boundary
people could not apply. Contested spans are stripped of annotator identity,
shuffled under a fixed seed, and adjudicated blind. The adjudicated gold set is
frozen before any gate is scored against it.

The blind false-positive pass follows the same pooling rule as Phase B: the
judge sees the posting and proposed concept, never which signal or candidate
rule admitted it. Arm identity and sampling weight are rejoined afterwards.

## Candidate signals to test

The issue names four plausible signals. None is promoted to a requirement in
advance.

### Position in the posting

Record title versus description, normalized relative offset, and section class
when a deterministic section parser can identify one: requirements,
preferred, stack or tools, responsibilities, company description, benefits,
legal, and unknown. Test both the raw buckets and coarse groups. In particular,
measure whether requirements and stack sections improve precision without
discarding legitimate skills mentioned in responsibilities.

### Use by more than one employer

Record distinct postings, employers, sources, and publication weeks. Test
support thresholds of one, two, and three employers. Employer support is
calculated within the split's full unlabelled corpus, never by counting a
duplicate template several times. The singleton arm remains in the comparison:
requiring recurrence could systematically reject the newly released products
unknown preservation exists to retain.

### Name-like versus prose behaviour

Freeze transparent features rather than an impressionistic label: token and
character count, capitalization pattern, acronym shape, digits, punctuation,
domain-like suffix, noun-phrase shape, and whether the same normalized string
appears in longer clauses. Test these features singly and in small documented
combinations. A proper-noun requirement is not assumed; `tapeout` is the kind
of lowercase technical term such a shortcut would lose.

### Corpus distribution

Record document frequency, employer concentration, source count, section
entropy, template concentration by description hash or near-duplicate group,
and spread across publication weeks. Test whether broad distribution predicts
legitimacy and whether concentration predicts boilerplate. Raw frequency alone
gets its own arm because Phase B showed that high document frequency can select
an employer footer rather than a skill.

### Candidate rules

The development comparison includes:

1. admit every unresolved candidate;
2. each signal family alone;
3. recurrence plus position;
4. name behaviour plus position;
5. distribution plus position;
6. a small conjunction using the best calibration-safe signals.

Threshold grids and feature calculations are committed before calibration is
scored. Rules stay short enough to render as evidence on a stored unknown; an
opaque classifier is out of scope for the first gate. The selected rule is the
highest-recall calibration rule whose precision interval clears the promotion
floor below. Ties choose the simpler rule, then the rule with fewer singleton
false rejections.

## Scoring and approval rule

A candidate finds a gold unknown when its evidence span overlaps the gold span.
Matches are one-to-one within a posting. Labels do not need to string-match,
for the same reason Phase B scored by span: naming variation is what canonical
concepts exist to resolve.

Primary metrics:

- precision among admitted unknowns after weighted blind adjudication;
- end-to-end recall over all fresh gold unknown posting-and-skill pairs;
- admissions per 1,000 postings;
- false-admission rate for boilerplate, legal text, and job duties.

Conditional gate recall over gold unknowns that the frozen proposer emitted is
reported separately, so a proposer miss is distinguishable from a gate
rejection. The approval floor applies to end-to-end recall because #47 and #48
can store only what survives both stages. Secondary slices include category,
requirement flag, source, sector, posting position, token length, singleton
versus multi-employer use, and named-looking versus lowercase prose-like forms.
A slice with fewer than 30 gold positives is descriptive only.

Confidence intervals use 10,000 paired cluster-bootstrap resamples. Employer is
the outer cluster and posting the inner unit, matching the employer-level split
and the fact that templates correlate within an employer. Unequal negative
sampling is corrected with recorded inverse-probability weights. The report
also gives the design effect and effective sample size.

The proposed promotion floor, frozen before calibration, is:

- point precision at least 0.90 and its 95% lower bound at least 0.85;
- point recall at least 0.70 and its 95% lower bound at least 0.60;
- for each required negative slice with at least 100 judged candidates, a
  false-admission point estimate no greater than 0.05 and a 95% upper bound no
  greater than 0.10.

Precision is deliberately the harder constraint. An unknown is optional
enrichment; storing another free-text-noise population would undo the Phase B
decision. The recall floor still prevents a rule that achieves perfect
precision by accepting only repeated uppercase product names.

Only the selected, versioned rule is run on the final holdout, once. A failure
is a result. Revising a signal, threshold, vocabulary, or proposer creates a
new rule version and requires a new employer-disjoint holdout; the existing
holdout becomes development evidence and is never called held out again.

## What an admitted unknown carries

An admitted occurrence must retain enough information to reproduce the
decision without storing provider prose:

- stable unknown identifier and normalized surface form;
- posting and provenance identifiers;
- description hash and evidence offsets;
- category and requirement flag;
- extractor, canonical vocabulary, candidate proposer, and gate-rule versions;
- the signal values used by that rule and its named admission reasons;
- first-seen and last-seen timestamps.

Corpus support counts are a versioned snapshot, not mutable facts silently
rewriting an old decision. Reprocessing under a new snapshot or rule produces a
new decision version atomically, as #47 and #48 require.

## Promotion from unknown to canonical

Admission is not canonicalization. It permits an evidence-bearing unknown to
be stored provisionally. Promotion is a reviewable vocabulary change:

1. Aggregate admitted occurrences by normalized form and candidate alias
   groups while preserving every occurrence's evidence.
2. Queue a review when the form reaches the versioned review policy, such as
   support from two employers, or when a curator nominates an important
   singleton. Recurrence triggers review; it does not automatically create a
   concept.
3. Resolve the candidate to an existing concept and add an alias, create a new
   canonical concept, or reject it as noise. A new concept receives a stable
   identifier, preferred label, aliases, category, and optional ESCO mapping.
4. Ship that decision as a versioned vocabulary-data change with tests for the
   accepted forms and known false positives.
5. Reprocess historical occurrences idempotently. Mapped unknowns point to the
   canonical concept, keep their original evidence and gate versions, and
   retain a redirect from the old unknown identifier so stored history is not
   orphaned.

A rejection suppresses the candidate only in a new gate or vocabulary version;
it does not erase the evidence behind an earlier decision.

## Cost

The positive rate makes annotation, not code, the expensive part.

| work | planning assumption | estimated effort |
| --- | --- | ---: |
| Corpus collection, manifest, split, and validation tooling | One reproducible measurement path, no application integration | 16–24 hours |
| Two independent focused passes | About 834 postings at 6–8 minutes per posting per annotator | 167–223 hours |
| Blind adjudication | About 300 positives plus disagreements | 15–24 hours |
| Old-pool, calibration, and holdout candidate judgement | Up to 2,200 pooled candidates | 18–28 hours |
| Scoring, bootstrap, report, and reproduction | Calibration plus one final run | 16–24 hours |
| **Total** | Expected case | **232–323 person-hours** |

The first 25-posting batch records actual minutes and disagreement rates, then
updates the effort forecast without changing sample or scoring thresholds. At
the observed Phase B tail rate this is roughly six to eight person-weeks, plus
calendar time for at least 3,000 genuinely new postings to appear. If the rate
is lower, the 400-posting cap per split prevents an open-ended annotation job
and the result is reported as underpowered.

That cost is the blocker #130 needs to record. Implementing the gate first
would not remove it; it would only spend the held-out set after the rule had
already seen the answers.

## Ordered outputs

The order is part of the design:

1. Commit this plan and the delivery-plan correction.
2. After #46, commit the frozen vocabulary/proposer versions, corpus manifest,
   split, seeds, and annotation-guide supplement.
3. Complete both independent passes and adjudication. Freeze development and
   calibration annotations, and hash-seal the unrevealed final annotations.
4. Test the candidate signals, select one rule on calibration, and commit the
   rule version and scoring implementation.
5. Release the already sealed final-holdout annotations, run the scorer once,
   and commit a result that quotes the corpus, gold-set, rule, and scorer
   commits.
6. Implement persistence only if the rule clears the pre-registered floor.

The committed measurement artifacts contain counts, hashes, offsets,
annotator-authored labels, versions, and decisions. Provider descriptions,
scratch databases, and fetched payloads remain outside Git.

## Delivery-plan correction

The delivery plan currently says this decision is needed “Before #46 ships.”
That reverses the dependency. #46 explicitly excludes the gate, and #130
depends on #46 because a canonical resolver is required to identify an
unknown. The correct gate is:

> Decide #130 after #46 defines canonical concepts, and before #47 or #48
> persists the first extracted unknown.

This keeps #46 buildable while preventing either extraction path from storing
unmeasured free text.

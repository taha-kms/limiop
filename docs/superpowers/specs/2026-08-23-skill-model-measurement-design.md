# Measuring what a skill is — B1 methodology

This is the design for the measurement that decides SkillSync's skill model. It
is written to be approved and then executed unchanged, because several of its
guarantees come from doing things in a fixed order rather than from doing them
well.

The decision it feeds is the one the [delivery plan](../../delivery-plan.md)
calls the hinge: free-text tokens, a curated list, and ESCO produce three
different databases and three different products, and #46, #47, #48, #49, #53,
manual onboarding, and every analytics query read off whatever it decides.

This document is the methodology only. The results get their own report.

## What this measures, and what it does not

It measures how much of the skill content of real job postings each candidate
vocabulary can find, and what each one misses.

It does not measure CV-side coverage, because no CVs exist. The assumption is
that job-side coverage proxies CV-side coverage. That is an assumption, it is
load-bearing, and it is not tested here.

## Scope decisions already made

| Decision | Value |
| --- | --- |
| Language | English only for v1. German is measured and reported, not served |
| What counts as a skill | Everything ESCO calls a skill, typed by sub-pillar |
| Gold set | Two independent annotators, adjudicated, n = 80 postings |
| Sampling unit | The posting |
| Corpus | Both sources, Greenhouse widened to ~15 mixed boards for the snapshot |

Broad skill scope was chosen deliberately over a technical-only set. It carries
two known risks, and the design answers both rather than accepting them:
annotator agreement is weaker across a fuzzy boundary, so agreement is measured
and reported instead of assumed; and a matcher can score points on `teamwork`,
so document frequency per skill is recorded, making a skill's lack of
discriminative value a number rather than an argument.

Because the scope is broad, every gold mention is **typed** by ESCO sub-pillar.
Narrowing the production scope later is then a filter. Widening it later would
mean annotating again.

## Constraints

Three rules the experiment can be checked against.

### Anti-circularity

**The gold set is produced without reference to any candidate vocabulary, and
is committed before any vocabulary is scored against it.**

Using a vocabulary to find mentions and then measuring what fraction of those
mentions the vocabulary covers returns 100% by construction. This repository
has shipped that error four times, in different disguises, so the protection
here is ordering rather than care: annotate, freeze, commit, and only then
build and score. The commit SHA of the frozen gold set is quoted in the results
report, so the order is auditable after the fact.

### Determinism

Fixed seeds, pinned vocabulary versions with recorded file hashes, scripted end
to end. A number that cannot be reproduced is not evidence. This also mirrors
what #47 and #48 require of the extractor that eventually ships.

### No provider prose in committed artifacts

External job data is untrusted and is never logged or republished. A measurement
does not suspend that rule, and the presentation of this design contradicted it
by proposing to store verbatim spans. It is resolved by separating two things
that are easy to conflate:

- **A span is provider prose.** It is recorded as `start` and `end` character
  offsets into the description, plus the SHA-256 of that description. The offsets
  locate the evidence; they do not reproduce it. The hash means a posting edited
  later is detected as stale rather than silently mis-scored.
- **A skill label is the annotator's word.** `Kubernetes`, `stakeholder
  management`, `German (C1)`. It is a name for a concept, authored by the
  annotator, and naming the concepts is the entire object of the exercise. A
  name is not a quotation, and a vocabulary made of names is what this phase
  exists to produce.

Two mechanical rules keep the second from becoming the first:

1. A label is at most four words and 64 characters. Anything longer is a copied
   clause, not a name, and fails validation.
2. A label is a canonical name, not the words as they appeared. If a posting
   says `must be comfortable owning services end to end`, the label is
   `service ownership`, not the clause.

A short technical name will sometimes be character-identical to the text it came
from, because that is what naming a technology looks like. That is not what the
rule protects against.

Intermediate files that do contain description text stay in the scratch
directory and are never added to git.

## Procedure

The steps are ordered. Several guarantees depend on the order, and those are
marked.

### 1. Corpus snapshot

Configure a wider Greenhouse board list of roughly fifteen boards, chosen to
include employers outside engineering, as a snapshot-only configuration that
does not change the shipped default and does not pre-empt #120. Every board
token is verified against the boards API before the list is fixed, rather than
assembled from remembered company names; a board that does not respond is
replaced and the substitution recorded.

The correction can fail, and what failure means is fixed now rather than
afterwards. Greenhouse's install base skews heavily toward technology
employers, so a list of fifteen responding boards may still be thirteen
engineering shops, which would spend the ingest and buy none of the correction.
The achieved mix is recorded by sector, not merely by count. **If fewer than
five of the boards are employers outside engineering, the bias stands**: the
corpus is reported as tech-heavy, coverage figures generalize only to a
catalogue that looks like this one, and the limitation is stated in the results
rather than quietly absorbed. A technical dictionary looks far better than it
is on a corpus of technology employers, and that is the specific way this
measurement could mislead the decision it exists to inform.

Run both sources to exhaustion into a scratch database.

Committed artifact: a manifest of counts by source, board, and employer, the
observed date range, the number of cross-source duplicate pairs, and the
per-posting description hashes. The database itself is discarded — the snapshot
is the manifest, not the server.

### 2. Language identification

Detect the language of every posting with a deterministic detector. `langdetect`
is excluded because it seeds from a random source and returns different answers
across runs; `py3langid` or `lingua` are the candidates, and the choice is
recorded with its version.

Reported: the DE / EN / other split, and therefore the share of the catalogue
that an English-only v1 structurally cannot serve. That number is useful whatever
wins.

The detector is itself checked. Annotators record the language they observe on
each sampled posting, which yields a measured detector error rate over 80
postings at no extra cost.

The per-source split is read here, before sampling, because it decides what the
sample can support. Arbeitnow is the German-heavy half, so the English filter
falls on it unevenly, and proportional allocation could leave the Arbeitnow
stratum at a dozen postings. That is enough for pooled recall and not enough for
any per-source claim. If a stratum lands that thin it is reported as thin, and
no per-source figure is drawn from it. A stratified sample must not be allowed
to imply a balance it does not have.

### 3. Sampling

Frame: postings detected as English.

Stratified by source, and within Greenhouse by board, with proportional
allocation and random selection inside each stratum under a fixed seed.

n = 80 postings.

**Ordering matters here.** The sampled identifiers and the seed are committed
before annotation begins, so the sample cannot be adjusted after anyone has
seen what is in it.

### 4. Annotation guide

Written and frozen before any posting is read.

It defines a mention as a contiguous span of the description that asserts a
skill. It fixes the categories to ESCO's four sub-pillars — knowledge, skills,
transversal skills, and language skills. It records a `requirement` flag of
`required`, `preferred`, or `unclear`, because a nice-to-have and a hard
requirement are not the same signal and separating them later is impossible.
It excludes years of experience, degrees, salary, and seniority titles. It
states the labelling rules from the previous section.

### 5. Two independent annotation passes

Two annotators work from the frozen guide: this session, and a fresh-context
agent. Neither sees any candidate vocabulary, and neither sees the other's
labels.

**Ordering matters here.** Both passes complete before either is compared, and
before any vocabulary is built.

### 6. Agreement

Cohen's kappa is not computable for this task. Kappa models chance agreement
over a closed label set, and this is open-vocabulary annotation where labels are
invented as the annotator reads. The standard measure in that case is
inter-annotator F1, taking one annotator's set as truth and the other's as
prediction.

Two figures are reported, because they fail differently:

- **Set-level F1** per posting, over skill labels. Do the annotators agree on
  what the posting requires?
- **Span-level F1**, requiring the offsets to overlap. Do they agree on where it
  was said?

Agreeing on the skill while disagreeing on the span is a minor problem.
Disagreeing on the skill is a definition problem, and if set-level F1 is low the
guide is at fault and gets revised and re-run rather than adjudicated over.

### 7. Adjudication and freeze

Disagreements are resolved in a third pass. Two things about how.

**A gold mention carries every name it was given, not one winning name.** It is
a span, a category, a requirement, and the set of labels both annotators used
for it. Adjudication therefore never picks between `product demonstration` and
`product demos`; it only decides the contested question, which is whether a span
is a skill mention at all. This matters because one of the two annotators is
also the party who will build the curated arm, and letting that annotator choose
the canonical names would hand their arm an advantage that has nothing to do
with coverage. The alias sets are a result in their own right.

**Contested spans are adjudicated blind.** A span marked by only one annotator
is stripped of which annotator marked it, shuffled under the recorded seed, and
judged against the guide alone by a third fresh-context agent.

Committed together: the gold set, the guide, the sample, and the seed. Everything
downstream quotes that commit SHA.

### 8. The arms

Three candidate vocabularies, matching the three products the delivery plan
names.

**A — Free text.** No vocabulary. Lowercased unigrams through trigrams, English
stopwords removed, retained when document frequency falls inside a band: at
least 3 postings, and at most 25% of the English corpus. Frequent enough to be
more than noise, rare enough to discriminate. Those endpoints are fixed here,
before anything is scored, because choosing them afterwards is choosing the
result.

**B — Curated list.** Hand-built, with aliases, under a fixed effort cap: the
1000 highest-document-frequency candidate terms from the disjoint slice are
reviewed once, and those that name a skill are kept with their obvious aliases.
One pass, no iteration against any score. The resulting size is recorded rather
than targeted.

**Ordering matters here.** It is built only from postings disjoint from the gold
sample. Disjointness is what prevents it from being tuned toward the answer, and
it is checked mechanically: the build script refuses to read a sampled posting.

**C — ESCO.** The skills pillar, English preferred and alternative labels, from
a pinned version with the download date and file hash recorded. ESCO is free to
reuse under Commission Decision 2011/833/EU, with attribution required under
CC BY 4.0; the attribution is added where the vocabulary ships.

Matching, for B and C, is longest-first surface matching on word boundaries —
the technique `backend/app/modules/jobs/vocabulary.py` already uses for workplace
phrases, so each arm reflects a mechanism this codebase would plausibly ship.

Every arm emits `(skill label, matched span)` per posting, which is the evidence
#47 and #48 require anyway.

### Considered and rejected: Lightcast Open Skills

Thirty-four thousand skills, mined from real postings, which is exactly the shape
that would suit this problem. It is not an arm because access is now a
contract-based API with no bulk download, refreshed every two weeks. A remote
vocabulary that changes underneath the extractor cannot satisfy #47 and #48's
requirement that extraction be deterministic and versioned, and the licence is
negotiated per customer rather than open.

### 9. Blind adjudication of false positives

Precision needs extracted pairs that are not in the gold set judged: is each a
real skill mention the annotators missed, or a false positive?

**Sampled, not exhaustive, and the cap is recorded.** Three arms over eighty
postings, one of them emitting every 1-to-3-gram in a frequency band, can
produce thousands of candidates, and judging all of them would cost more than
the answer is worth. Up to 200 candidates per arm are drawn at random under the
recorded seed and judged; precision is reported as an estimate with a confidence
interval rather than as a census. The number drawn and the number skipped are
both reported, because a cap nobody mentions reads as full coverage.

It runs after the arms, because the arms produce the candidates. It carries the
same contamination risk the gold set is protected from, and the presented design
left it uncovered. An adjudicator who can see that ESCO
proposed `communication` is not judging the mention, they are judging ESCO.

So the candidates from all arms are pooled, stripped of which arm produced
them, deduplicated, and shuffled under the recorded seed before being judged.
The adjudicator sees a posting and a candidate skill, and nothing about where
the candidate came from. Arm identity is rejoined afterwards, from the mapping
kept aside.

**Ordering matters here.** Pooling and stripping happen before any judgement,
not after.

## Measurements

All against the frozen gold set.

### The unit is the (posting, skill) pair, matched by span

Recall and precision are computed over `(posting, gold mention)` pairs. A
posting that says `Python` three times contributes one pair, not three.

**An arm finds a gold mention when its matched span overlaps the gold span.**
Not when its label matches the gold label.

This fills a hole the design left rather than revising a pre-registered choice:
the matching rule was never specified, and it is fixed here on principle, before
any arm has been built or scored. It has to be label-agnostic, because the
annotation itself showed that names are not stable — where both annotators
marked the same span, 36.7% of the time they named it differently. Scoring by
label would have measured naming convention rather than coverage, and it would
have done so asymmetrically: ESCO's preferred labels are written in ESCO's
register and would rarely string-match an annotator's wording, while a
hand-built list assembled by one of the annotators inherits that annotator's
naming for free. The comparison would have been decided by an artifact.

Span overlap is lenient in one direction worth naming: a free-text arm can claim
a hit for matching `management` inside `supplier performance management`. That
bias favours the free-text arm, which is to say it runs against the conclusion
the naming evidence already points toward, so it is a conservative error here
rather than a flattering one.

This needs stating because the document defines a mention as a span, and span
recall would answer a question nobody asked. What ships is a skill set per job
with evidence attached — #47 and #48 store exactly that — so an extractor that
finds one of three occurrences has lost nothing the product cares about. Spans
remain the evidence, and they are scored, but only in the span-level agreement
figure.

| Measurement | What it decides |
| --- | --- |
| Recall, overall and per ESCO category | The headline coverage figure |
| Precision, with false positives adjudicated in a second pass | Where a dictionary actually fails |
| Short-token precision, matches of three characters or fewer, reported separately | `R`, `Go`, `C`, `SAS`, and `IT` inside `mit` |
| The tail: gold mentions no arm found, listed and categorized | Real technical skills means curated loses; vague competencies means ESCO's breadth is noise |
| Document frequency per extracted skill | A skill in 90% of postings carries no signal. The `teamwork` problem as a number |
| Ambiguity: gold mentions mapping to more than one ESCO concept | ESCO's specific failure mode |
| Vocabulary size, build effort, and update story | The costs that do not appear in an F1 |

### Confidence intervals must respect clustering

Recall is a proportion over mentions, but mentions are not independent. Postings
are sampled; mentions arrive in clusters, and a posting that mentions Kubernetes
disproportionately also mentions Docker and Terraform. Pooling mentions and
applying a Wilson interval would treat perhaps a thousand correlated
observations as a thousand independent ones and report an interval several times
narrower than the evidence supports.

The posting is the primary sampling unit, so:

- **Cluster bootstrap over postings.** Resample the 80 postings with
  replacement, ten thousand times, recomputing each metric per resample; report
  the percentile interval. This matches the sampling design and assumes little.
- **Report the design effect** alongside each interval, and the intra-cluster
  correlation of mention outcomes. Making the inflation visible is the point: a
  design effect of three means the 80 postings are worth roughly 27 independent
  mentions' worth of precision, and a reader deserves to see that rather than
  infer it.
- **Compare arms with a paired cluster bootstrap on the difference**, resampling
  the same postings for both arms. The decision rule is stated in percentage
  points of difference, so the difference is what needs an interval — and pairing
  removes the between-posting variance that both arms share.

An interval that spans the decision threshold means the measurement did not
separate the arms. That is a valid outcome and is reported as one.

## The decision rule, fixed in advance

Recorded before running so the outcome cannot be rationalized afterwards.
Thresholds are read against the paired cluster-bootstrap interval on the
difference, not against point estimates alone.

1. **Curated recall within 5pp of ESCO, and better precision → curated wins.**
   "Within 5pp" means the paired interval on the recall difference does not
   extend past 5pp in ESCO's favour. "Better precision" means the paired
   interval on the precision difference excludes zero. Smaller, ours, fully
   deterministic, and no external dependency.
2. **ESCO ahead of curated by more than 10pp recall, with the extra hits in
   categories the product needs → ESCO wins.** The qualifier matters: extra
   recall concentrated in transversal skills that no matcher should weight is
   not a reason to adopt a 13,000-concept taxonomy.
3. **Free text with high recall and low precision, and an unstable tail →
   rejected as a store.** It may still be retained as a discovery aid for
   maintaining a curated list, which is a different job.
4. **No arm reaching roughly 60% recall → dictionary-only extraction is
   insufficient, and a hybrid is evaluated.** Read against point estimates: if
   no arm's recall reaches 60%, the rule fires. Not the least-bad dictionary. A
   floor missed by every arm is evidence about the method, not a ranking among
   its instances.

### What hybrid means, if rule 4 fires

Named now so the fallback is a plan rather than a gesture. Both variants keep
the determinism #47 and #48 require, and they keep it in different places:

- **Deterministic at runtime, learned offline.** A statistical or model-based
  pass runs at vocabulary-build time to *propose* entries, which are reviewed
  and accepted into a frozen, versioned dictionary. Runtime extraction stays
  pure dictionary matching. Non-determinism is confined to authoring, where a
  human already gates the output.
- **Learned at runtime, pinned by weights.** An extraction model with fixed
  weights and a fixed seed, versioned by model hash. Deterministic in the sense
  the issues require, at the cost of a much heavier artifact to version and
  reproduce.

If rule 4 fires, both are evaluated against the same frozen gold set, under the
same metrics, and must clear the same 60% floor to be adopted.

## Outputs

- This design.
- The corpus manifest: counts and hashes, no text.
- The annotation guide, the sample, the seed.
- The gold set, frozen and committed before any arm is scored.
- A results report, quoting the gold set's commit SHA.

The scratch database is discarded. Nothing but counts, hashes, identifiers,
offsets, and annotator-authored labels is committed.

## Limitations

- **No CVs exist.** Job-side coverage only, assumed to proxy CV-side coverage.
- **English only.** The German share of the catalogue is reported and unserved.
- **One annotator also builds the vocabularies.** Ordering and freezing reduce
  this; they do not remove it. The fresh-context second annotator and the
  disjoint curated-list build are the concrete mitigations.
- **Fifteen boards is not a random sample of employers.** Better than three, and
  still a convenience sample. Coverage figures generalize to a catalogue that
  looks like this one.
- **Eighty postings.** The cluster bootstrap will say how much that buys, and it
  may say the arms are not separated.

# Results — which skill vocabulary covers real postings

Scored against the gold set frozen at commit `d505459`, before any arm was
built or run. 2059 mentions over 78 of 80 sampled postings. Methodology and
decision rule: `../superpowers/specs/2026-08-23-skill-model-measurement-design.md`.

## The numbers

| arm | vocabulary | spans matched | recall | 95% CI | design effect | strict precision |
| --- | --- | --- | --- | --- | --- | --- |
| free text | 77,407 terms | 20,563 | **0.974** | [0.963, 0.984] | 2.37 | 0.151 |
| curated list | 184 forms | 4,298 | **0.412** | [0.381, 0.443] | 2.17 | 0.227 |
| ESCO | 65,850 labels | 2,565 | **0.285** | [0.261, 0.308] | 1.47 | 0.233 |

Paired differences in recall, resampling the same postings for both arms:

| comparison | difference | 95% CI |
| --- | --- | --- |
| curated minus ESCO | **+0.127** | [0.095, 0.160] |
| curated minus free text | −0.562 | [−0.596, −0.530] |
| ESCO minus free text | −0.690 | [−0.712, −0.666] |

Design effects near 2.2 on the two dictionary arms: eighty postings buy roughly
what thirty-six independent mentions would. Pooling mentions and ignoring the
clustering would have reported intervals about half as wide as the evidence
supports.

## Reading them

**Free text's recall is saturation, not coverage.** 77,407 terms produce 20,563
matched spans against 2,059 gold mentions, so nearly every gold span overlaps
something. The span-overlap matching rule is lenient in exactly this direction,
which the design accepted in advance because the bias runs toward free text
rather than against it. A vocabulary that matches everything cannot rank
anything, and 0.151 precision is what that looks like. Decision rule 3 rejects
it as a store.

**Curated beats ESCO on recall, and the interval excludes zero.** 184
hand-written surface forms found more of the gold set than 65,850 ESCO labels.
That is not a result anyone should have predicted from vocabulary size, and it
says something specific: ESCO's labels are written in ESCO's register
(`manage procurement of software`) and job postings are not.

**Precision is a tie, and it is a lower bound.** 0.227 against 0.233, intervals
overlapping. Both figures count a match as correct only when it lands on a gold
mention, and the gold set is not exhaustive, so both understate. The blind
false-positive pass that would have resolved this was **not run** — recorded
here rather than left as an implied census.

## The tail

38 gold mentions (1.8%) were found by no arm at all. It is small only because
free text blankets the text; against the dictionary arms alone the miss rate is
far higher.

What the tail contains is the informative part: `QGIS`, `LucaNet`, `NIST`,
`WES`, `Sage 200`, `nue.io`, `tapeout`, `design for test`, `analog
mixed-signal`, `post-silicon bring-up`, `CSPM`, `SNMP`, `YAML`,
`Wirtschaftsprüfer`, `life cycle assessment`, `geodatabases`. 28 of 38 are
`knowledge`: named products, standards, and niche technical concepts. These are
exactly the things a fixed list is worst at, because they arrive faster than
anyone curates.

## Against the decision rule

The rule was fixed before running. Applying it honestly requires naming a
conflict it did not anticipate.

1. **Curated within 5pp of ESCO and better precision → curated wins.** Curated
   is 12.7pp *ahead* on recall, so the recall clause is satisfied. The precision
   clause is not: 0.227 against 0.233 with overlapping intervals is not "better
   precision", and the pass that would settle it was not run. **Does not fire.**
2. **ESCO ahead by more than 10pp recall → ESCO wins.** ESCO is 12.7pp behind.
   **Does not fire.**
3. **Free text with high recall and low precision → rejected as a store.**
   **Fires.** It may still be useful as a discovery aid for maintaining a list,
   which is a different job.
4. **No arm reaching roughly 60% recall → dictionary-only extraction is
   insufficient, evaluate a hybrid.** Read literally, this does not fire,
   because free text reaches 97.4%. Read against the arms that survive rule 3,
   it does: curated is at 41.2% and ESCO at 28.5%, and neither is close.

**The two readings disagree, and the disagreement is the finding.** The only arm
clearing the floor is the one rule 3 disqualifies, and it clears it by matching
everything. That is not a vocabulary winning; it is the floor being cleared by
an arm that cannot serve the purpose. The substantive reading is that
dictionary-only extraction did not reach the bar, and the hybrid named in the
design should be evaluated.

That reading is a judgement, not a computation, and it is flagged rather than
taken.

## What limits these numbers

- **ESCO is partial.** The walk was stopped at 10,223 concepts of roughly
  14,000, so its recall is understated by some amount this measurement cannot
  quantify. Closing that gap would have to more than double ESCO's recall to
  change any conclusion, which is implausible but not measured.
- **The curated arm was handicapped by a rule I wrote.** Ranking candidates by
  document frequency spent the budget on equal-opportunity boilerplate and on
  one employer's posting footer, which appears in roughly 500 postings. A
  thoughtfully curated list of the same size would do better, so 0.412 is a
  floor for curation rather than a verdict on it.
- **`own` was in the curated list** as an alias for ownership and matched 57
  times as the ordinary verb. My error; left in place because the arm was frozen
  before scoring.
- **Strict precision is a lower bound** for every arm, and the blind
  false-positive pass was not run.
- **English only**, and 27% of the catalogue is not English.
- **Job side only.** No CVs exist, and the assumption that job-side coverage
  proxies CV-side coverage is untested.

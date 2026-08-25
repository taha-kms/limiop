# Unknown-skill gate evaluation

The requested permissive gate cannot be scored from the committed measurement
artifacts. The decision is therefore **closed admission**: unresolved candidates
are rejected until a rule can be measured against identifiable genuine unknowns
and labelled junk. This is a rule an implementer can apply, and it does not turn
the rejected free-text arm back into storage by assumption.

## Scoring rule

The annotation guide remains the definition of a genuine skill mention. For
each candidate gate, the required scores are:

- genuine-unknown admission: admitted gold unknowns divided by all gold
  unknowns;
- junk admission: admitted labelled junk candidates divided by all labelled
  junk candidates.

The same candidate record must carry its posting, normalized form, evidence
span, and employer so recurrence rules and shape rules are evaluated on the
same population. A gold mention cannot be treated as unknown without the
frozen vocabulary arms' resolution result, and absence from the exhaustive
gold set cannot be treated as junk because the blind false-positive pass was
not run.

## Artifact audit

Run from the repository root:

```console
python3 - <<'PY'
import json
import re
from pathlib import Path

root = Path("docs/skill-model-measurement")
gold = json.loads((root / "gold-set.json").read_text())
sample = json.loads((root / "sample.json").read_text())["sample"]
adjudication = [
    json.loads(line)
    for line in (root / "in-progress/adjudication.jsonl").read_text().splitlines()
]
results = (root / "results.md").read_text()
rejected = [row for row in adjudication if not row["is_mention"]]
print(json.dumps({
    "gold_mentions": len(gold["gold"]),
    "gold_postings": len({row["posting"] for row in gold["gold"]}),
    "gold_records_with_arm_result": sum("arm_hits" in row for row in gold["gold"]),
    "reported_no_arm_tail": int(re.search(r"(\d+) gold mentions .*no arm", results).group(1)),
    "reported_named_products_and_standards": int(re.search(r"(\d+) of 38 are", results).group(1)),
    "sample_records": len(sample),
    "sample_records_with_description": sum("description" in row for row in sample),
    "sample_records_with_employer": sum("employer" in row for row in sample),
    "adjudicated_rejections": len(rejected),
    "rejections_with_candidate_text": sum("label" in row for row in rejected),
    "rejections_with_posting": sum("posting" in row for row in rejected),
}, indent=2))
PY
```

Output from 2026-08-25:

```json
{
  "gold_mentions": 2059,
  "gold_postings": 78,
  "gold_records_with_arm_result": 0,
  "reported_no_arm_tail": 38,
  "reported_named_products_and_standards": 28,
  "sample_records": 80,
  "sample_records_with_description": 0,
  "sample_records_with_employer": 0,
  "adjudicated_rejections": 181,
  "rejections_with_candidate_text": 0,
  "rejections_with_posting": 0
}
```

The report names 16 examples from the 38-miss tail, but neither the structured
gold set nor another committed artifact marks all 38 members or the 28-product
subset. The corpus manifest contains aggregate employer counts, not a
posting-to-employer map. The sample contains only posting keys and description
hashes. The free-text candidate pool and descriptions were deliberately not
committed, and the 181 rejected contested annotations cannot be rejoined from
their blind IDs to candidate text or postings. Consequently there are zero
scorable target records and zero scorable junk records, despite the aggregate
counts.

## Candidate rules and results

Normalization below means Unicode case-folding, replacing runs of whitespace,
hyphens, and underscores with one space, and trimming the result.

| candidate | exact rule | genuine unknowns admitted | junk admitted | result |
| --- | --- | ---: | ---: | --- |
| Posting frequency | Admit when the normalized form occurs in at least 2 distinct postings. | Not scoreable (0 identifiable records) | Not scoreable (0 labelled records) | No candidate occurrences are committed. |
| Employer diversity | Admit when the normalized form occurs for at least 2 distinct employers. | Not scoreable (0 identifiable records) | Not scoreable (0 labelled records) | No per-posting employer map is committed. |
| Shape | Admit 1–4-token, 2–64-character forms containing a Unicode letter where at least half of non-whitespace characters are alphanumeric. | Not scoreable (0 identifiable records) | Not scoreable (0 labelled records) | The target subset and junk candidate text are absent. |
| Frequency plus shape | Admit only when both the posting-frequency and shape rules pass. | Not scoreable (0 identifiable records) | Not scoreable (0 labelled records) | Both required populations are absent. |
| Closed admission | Reject every unresolved candidate. | 0/38 (0.000) | 0 admitted (0.000 for any non-empty junk population) | Chosen. Target identities and candidate features are not needed to reject all. |

The figures are not replaced with scores over all 2,059 gold mentions. Those
mentions include known skills, and applying shape or recurrence rules to
annotator-authored labels would answer a different question. Nor are the 181
blind adjudication decisions counted as junk: they are contested annotation
spans, and their candidate mapping and rejection reasons are absent.
Closed admission is the one exception: its zero numerator follows directly
from the rule, so the aggregate 38-positive denominator is sufficient.

## Decision

**Reject every unresolved candidate for matching. Record it as an
observation.**

Two different things were being decided under one word. After the canonical
resolver returns no concept:

- The candidate is **never** written to `job_skills`, never promoted to a
  concept, and never reaches matching or analytics. There are no exceptions for
  frequency, employer count, capitalization, acronym shape, or token count.
  This is the closed rule the evaluation supports, and it is what protects
  matching from the population that scored 0.151 precision as free text.
- The candidate **is** written to `job_skill_mentions`, which nothing matches
  against. Recording an observation is not admitting a skill.

The second half is what makes the first half temporary rather than permanent.
The evaluation above failed for want of records carrying a candidate, its
posting, its employer, and its span together. That is exactly what the
observation table accumulates, from two sources running hourly against a
database that now persists. The gate becomes scoreable from production
observations rather than from a second hand-annotated corpus.

Each observation carries enough provenance to evaluate it later: the raw
extracted value as written, the normalized value where one exists, the job it
came from, when it was first and last seen and how often, and the version of
the extractor that produced it. Extractor version is separate from vocabulary
version: a change in either can explain why a term stopped resolving, and
without both recorded the two are indistinguishable.

Promotion out of the inbox is a later decision, made against those
observations, requiring the same evidence this evaluation could not find:
every candidate linked to a posting, normalized form, span, and employer; the
genuine-unknown population marked; junk labelled blind; and both admission
fractions reported.

The three permissive rules and their combination lose because none can be
scored against either required population. Choosing a threshold among them
would be choosing from intuition, which the issue forbids. Closed admission has
zero admissions by construction and is the only choice that cannot re-admit an
unmeasured junk population; it intentionally has zero unknown-skill recall
until the missing evidence exists.

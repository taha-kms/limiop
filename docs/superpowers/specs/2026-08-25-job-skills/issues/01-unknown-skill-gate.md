# 01 — Decide the unknown-skill gate, by measurement

## Why
The skill model decision preserves legitimate unknown skills and says plainly
that "legitimate" is load-bearing and unspecified: unrestricted free text was
85% junk, and preserving unknowns re-admits exactly that population unless
something decides which unknowns are real. Free text scored 0.151 precision.

This issue produces the rule. It is a decision, not a feature, and it must be
decided the way the skill model itself was — against the corpus, with numbers —
rather than by choosing a plausible threshold.

## What exists to measure against
- `docs/skill-model-measurement/gold-set.json` — the adjudicated annotations.
- `docs/skill-model-measurement/corpus-manifest.json` and `sample.json`.
- `docs/skill-model-measurement/results.md` — how the three vocabularies scored,
  and the finding that 28 of the 38 mentions no arm found were named products
  and standards.
- `docs/superpowers/specs/2026-08-24-skill-model-decision.md` — the decision this
  gate completes.

Read `results.md` and the annotation guide before designing anything. The point
is to extend that evaluation, not to start a new one with different rules.

## Scope
Propose at least three candidate gate rules and score them. Candidates worth
considering, though you are not limited to these:

- **Frequency across postings.** A mention is legitimate if its normalized form
  appears in at least N distinct postings. Vary N.
- **Employer diversity.** As above, but counting distinct employers, so one
  company's internal jargon repeated across its own postings does not qualify.
- **Shape constraints.** Length bounds, token count, rejection of sentence
  fragments and of forms that are mostly punctuation or digits.
- **Combinations** of the above.

Score each against the gold set: what fraction of genuine unknown skills does
it admit, and what fraction of junk does it also admit. The 28 named products
and standards are the population that must survive; sentence fragments and
boilerplate are the population that must not.

Write the result to
`docs/superpowers/specs/2026-08-25-job-skills/gate-evaluation.md`: the
candidates, the numbers, the chosen rule, and why the runners-up lost. Then
state the chosen rule in one paragraph that an implementer can follow without
reading the evaluation.

## Constraints
- Do not invent corpus data. If the artifacts are insufficient to score a
  candidate, say so and say what would be needed, rather than estimating.
- Report real numbers from code you ran. No illustrative figures.
- A rule that admits everything is not a rule. If every candidate admits most
  junk, that is a finding, and the honest output is that unknowns should not be
  stored yet.

## Out of scope
Implementing the gate, any schema, and any extraction. This issue ends with a
written, evidenced decision.

## Acceptance
- `gate-evaluation.md` exists and contains, for each candidate, the numbers it
  scored and the command that produced them.
- The chosen rule is stated unambiguously enough to implement.
- `docs/delivery-plan.md` records the decision in its settled list, with a link.

# The observation inbox, filled — 2026-08-29

Issue #205. The inbox has existed since #189 and held nothing, because the
extractor matches a vocabulary and cannot see a term outside it. Something had
to propose the terms the vocabulary does not already contain.

## What a run produces

Against the real boards, 250 records each from Arbeitnow and Greenhouse over a
1,252-posting catalogue:

| | |
| --- | ---: |
| Observations stored | 28,172 |
| Distinct terms | 7,736 |
| Terms under more than one employer | 1,062 |
| Postings carrying observations | 462 |
| `job_skills` rows | 7,654 |

Two identical Arbeitnow runs reported the same counts — 2,060 resolved and
12,416 unknown each time — so re-running an unchanged posting neither grows the
table nor moves an occurrence count.

## The rule, stated so it can be argued with

A candidate is a run of one to four adjacent tokens that reads like a named
thing: a capitalised run, or a token carrying punctuation no ordinary word does
(`node.js`, `CI/CD`, `C++`). A sentence's first word is not taken alone,
because every sentence capitalises one.

Overlapping runs are all proposed. `Amazon Web Services` also proposes
`Amazon Web` and `Amazon`, because which of them is the skill is exactly what
the accumulated evidence is meant to answer, and choosing here would answer it
with a guess.

Nothing filters the output. No frequency rule, no shape rule beyond the one
above — the whole point is that no such rule has been measured, and filtering
before measuring destroys the evidence a rule would need.

## German capitalises its nouns

The first attempt proposed `Erfahrung`, `Aufgaben` and `Bereich` across roughly
a hundred employers each. About a quarter of this catalogue is German, and in
German the capitalisation signal is grammar rather than naming.

Rather than detect the language, which needs a dependency `platform_skills`
refuses, the text is asked how much it capitalises. Measured over the 1,252
stored postings:

| | Median | p10 | p90 |
| --- | ---: | ---: | ---: |
| German-looking | 0.442 | 0.354 | 0.519 |
| English-looking | 0.134 | 0.112 | 0.179 |

The populations do not overlap, so the threshold sits at 0.25, between them
rather than at either edge. Above it only the punctuation signal is used, so
`node.js` is still proposed in a German posting and `Erfahrung` is not.

That correction alone removed 45% of the candidates: 149,231 mentions across
31,281 terms became 82,702 across 15,116.

A short text is not measured at all. One sentence naming two technologies is
already at 0.4 capitalisation, and gating on that would refuse every short
description for looking like a language it is not.

## Twenty read by hand

Twenty observations drawn at random from six postings, judged against the text
they were found in.

**Plausible skills — 6.** `GDPR`, `BI`, `GTM`, `IEC`, `Multimodal Neurons`,
`Based Interpretability`. Two are fragments of longer research terms, which is
the overlapping-runs rule working as intended rather than failing.

**Employer boilerplate — 6.** `San` and `Safety` and `Concrete` and `Neurons`
come from one employer's standard blurb listing its own papers;
`anthropic.com/careers` and `About Anthropic Anthropic` from its anti-scam
notice. All from the employer that contributes half the catalogue, which is the
distortion this repository has had to correct for at every stage.

**Noise — 8.** `and/or`, `e.g`, `Earnings`, `Customer`, `Do`,
`RESPONSIBILITIES Manage`, `Center Electrical`, `CesiumAstro` — a company name,
two sentence fragments, and a handful of ordinary capitalised words.

Roughly a third plausible. That is what an unfiltered generator produces and
what the promotion decision is meant to sort through; a generator whose output
was already clean would have had its judgment made for it.

## What the gate still refuses

Nothing generated here reaches `job_skills`. The admission gate decided in #190
is unchanged: a candidate is observed, never admitted, and a test asserts a
posting naming only unknown terms produces no skills at all.

## What this does not settle

Whether any of these terms should become concepts. That is #152, and it now has
input it did not have: 7,736 distinct terms, 1,062 of them under more than one
employer, each tied to the posting and the employer it was found in — which is
exactly the join the gate evaluation could not make.

The per-employer count is the number to promote on. `Senior` leads on employer
count at 35 and is not a skill; `Python` sits at 18 and plainly is. Frequency
alone will not separate them, and this document does not pretend it can.

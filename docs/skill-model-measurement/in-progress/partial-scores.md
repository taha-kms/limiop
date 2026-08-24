# Partial scores — two arms of three

ESCO is still downloading, so this is not the result. It is the two arms that
could be scored, recorded so the numbers exist before the third arrives and
cannot be quietly re-derived afterwards.

Scored against the gold set frozen at commit `868bc12`: 2059 mentions over 78
postings. An arm finds a gold mention when a span it matched overlaps the gold
span. Intervals are cluster bootstraps over postings, 10000 resamples.

| | free text | curated list |
| --- | --- | --- |
| vocabulary terms | 77407 | 184 |
| spans matched | 20563 | 4298 |
| **recall** | **0.974** [0.963, 0.984] | **0.412** [0.381, 0.443] |
| design effect | 2.37 | 2.17 |
| strict precision | 0.151 [0.142, 0.161] | 0.227 [0.206, 0.249] |
| short-token matches | 411 over 168 distinct terms | 411 over 7 distinct terms |
| short-token precision | 0.214 | 0.100 |
| gold found / missed | 2006 / 53 | 848 / 1211 |

Strict precision counts a match as correct only when it lands on a gold
mention, and the gold set is not exhaustive, so every figure in that row is a
lower bound. The blind adjudication pass exists to replace it.

## What these two numbers mean

**The free-text arm's recall is an artefact, and a predicted one.** 77407 terms
over 78 postings produce 20563 matched spans against 2059 gold mentions: the
arm blankets the text, so almost every gold span overlaps something. The
measurement design named this leniency in advance and accepted it because it
biases toward free text rather than against it. Recall of 0.974 at a precision
of 0.151 is not coverage, it is saturation, and a vocabulary that matches
everything cannot rank anything.

**The curated arm is small because the curation rule was poor.** 184 surface
forms found 41% of the gold set. The rule — review the thousand
highest-document-frequency terms from the disjoint slice — spent most of its
budget on equal-opportunity boilerplate and on one employer's posting footer,
which appears in roughly 500 postings and therefore dominates the frequency
ranking. That is a real finding about frequency-based curation and it is also a
handicap this arm did not earn.

Both design effects sit near 2.2, so the eighty postings buy roughly what
thirty-six independent mentions would. Pooling mentions and ignoring the
clustering would have reported intervals about half as wide as the evidence
supports.

## One error worth naming

`own` is in the curated list as an alias for ownership, and it matched 57
times, mostly as the ordinary verb in phrases like "own the roadmap". Together
with `ai` at 330 matches it accounts for most of that arm's short-token
matches, at a short-token precision of 0.100. It is exactly the failure the
design predicted for short tokens, it is my error rather than the method's, and
it stays in place because the arm was frozen before scoring.

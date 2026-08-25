# 02 — `platform/skills`, the shared extractor

## Why
Extraction runs on both sides: job text during ingestion, CV text on upload.
Same behaviour, two callers, so it is a shared library.

It cannot live in `platform_db`. The CI contract from #167 allowlists that
package to models, migrations, and the session factory, deliberately, to stop
it drifting into the data-access service that was rejected. A fourth package is
the answer that respects the rule rather than bending it.

## Scope
`platform/skills`, installable as `skillsync-platform-skills`, import name
`platform_skills`.

- A pure function of `(text, vocabulary) → mentions`. No I/O, no database
  access, no HTTP. It receives the vocabulary as an argument; it does not load
  it. Loading is the caller's business, because the caller knows whether it is
  inside an ingestion run or a web request.
- A `Mention` result carrying the surface form as written, its normalized form,
  the span, whether it resolved to a concept, and which concept if so.
- Depends on `skillsync-platform-db` **only if** it needs the vocabulary types.
  Prefer taking a plain mapping and depending on nothing, so the extractor can
  be tested without a database.
- Package configuration matching the other packages: `ruff.toml`, mypy, and a
  pytest configuration with the same coverage gate.

## Evaluate it on what survives, and say so

The full evaluation is not possible and will not become possible. The gold
set's posting text was never committed, and only 14 of its 78 postings are
still recoverable from the live catalog by hash — the other 64 have expired
from the board. That is roughly 350 of 2059 adjudicated mentions.

Score the extractor against those 14 postings and report precision and recall
as a **partial sanity check**, stated as such everywhere it appears. Do not
compare the result to the figures in `results.md`: those came from 80 postings
double-annotated with 1053 spans adjudicated blind, and a number from 14
postings is not the same measurement. Presenting them side by side would invite
exactly that comparison.

What the partial check is good for: catching an extractor that is broken,
tokenizing wrongly, or missing obvious matches. What it cannot do: tell you
whether this extractor is better or worse than the hand-written surface forms.

Report the recovered posting count and mention count alongside the scores, so
the reader knows the denominator. If fewer than 14 postings resolve when you
run it, report the number you actually got rather than the number written here.

## Update the boundary contract
`tests/architecture/test_boundaries.py` gains rules for the new package:
`platform_skills` must not import `app.*`, `job_ingestion`, FastAPI, Starlette,
or uvicorn. Add it to the CI workflow's install and test steps.

## Out of scope
Calling it from anywhere. Storing anything. The gate itself, which is #130.

## Acceptance
- `pip install -e platform/skills` succeeds and the package imports.
- Precision and recall against the gold set are reported as real numbers from a
  command you ran, alongside the figures in `results.md` for comparison.
- The extractor runs with no database and no network. Prove it.
- Boundary tests cover the new package and pass.
- Ruff, mypy, and the package's own tests pass.

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

## Evaluate it, do not just test it
The extractor is scored, not merely unit-tested. Run it against
`docs/skill-model-measurement/gold-set.json` and report precision and recall
against the adjudicated annotations. `docs/skill-model-measurement/results.md`
records what the hand-written surface forms achieved; this extractor should be
in that neighbourhood, and a large divergence in either direction means
something is wrong with the harness rather than being good news.

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

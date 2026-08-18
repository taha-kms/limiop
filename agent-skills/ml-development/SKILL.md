---
name: ml-development
description: Develop and modify SkillSync machine-learning and data-science code for CV parsing outputs, skill extraction, semantic representations, CV-to-job matching, recommendation ranking, model training, evaluation, inference, experiment reproducibility, and model artifact/version handling. Use whenever work changes files under SkillSync's ml directory or changes an ML-owned contract consumed by the backend, Airflow, data engineering, or analytics. Keep the core product usable without paid model APIs, prefer measurable baselines before more complex models, and follow repository task/Git rules separately.
---

# ML Development

## Goal

Build SkillSync ML features that are reproducible, testable, explainable enough for users, and justified by measured improvement. Keep training, evaluation, and inference separate. Do not make model complexity a substitute for evidence.

## Required Context

Before changing ML code:

1. Read `AGENTS.md`.
2. Read `docs/PROJECT_CONTEXT.md`.
3. Inspect existing `ml/`, backend contracts, Airflow callers, and data contracts affected by the task.
4. Follow the repository's issue, branch, commit, PR, testing, and Git-identity rules from `AGENTS.md`; do not duplicate or weaken them here.

## Ownership Boundaries

Keep ML responsibilities under `ml/` unless an existing repository convention says otherwise.

Prefer this separation:

```text
ml/
├── preprocessing/
├── features/
├── training/
├── evaluation/
├── inference/
├── experiments/
└── tests/
```

Keep these boundaries:

- Put reusable preprocessing and feature logic in normal Python modules.
- Put training orchestration logic in `ml/training/`.
- Put production prediction/ranking code in `ml/inference/`.
- Put metrics, evaluation datasets, and comparison logic in `ml/evaluation/`.
- Keep exploratory notebooks/scripts in `ml/experiments/`; move production-worthy logic into reusable modules before shipping it.
- Let Airflow schedule training/evaluation jobs, but keep ML implementation out of DAG definitions.
- Let FastAPI call stable inference interfaces; do not train models inside API requests.
- Keep data normalization, deduplication, and source ingestion in data-engineering code rather than duplicating them in ML.

Read [references/ml-architecture.md](references/ml-architecture.md) when adding or moving ML modules or changing cross-component contracts.

## Development Workflow

For every ML change:

1. Define the product behavior or metric that should improve.
2. Inspect the current baseline and data contract.
3. Implement the smallest valid baseline or change.
4. Add deterministic tests for preprocessing and contracts.
5. Evaluate on an explicit evaluation set using task-appropriate metrics.
6. Compare against the current baseline before promoting a more complex approach.
7. Record model/config/data provenance needed to reproduce the result.
8. Review latency, memory, privacy, and deployment impact.
9. Update backend/Airflow/data contracts only when the issue requires it.

Do not promote a model because it merely runs successfully.

## Matching and Ranking

Treat CV-to-job matching as a ranking problem, not just a single similarity number.

Start with understandable baselines such as:

- normalized skill overlap;
- TF-IDF plus cosine similarity;
- simple weighted combinations of semantic similarity and explicit skill overlap.

Introduce sentence embeddings or more advanced rankers only when evaluation shows a useful improvement.

Keep score components inspectable where practical. Prefer output that can support explanations such as:

```text
overall_match
semantic_similarity
skill_overlap
matched_skills
missing_skills
```

Do not use sensitive or irrelevant personal attributes to rank jobs.

Read [references/matching-and-ranking.md](references/matching-and-ranking.md) for scoring, ranking, caching, and leakage rules.

## Skill Extraction and ESCO

Treat skill extraction as a distinct task from job ranking.

- Normalize extracted skills against the project's canonical skill representation where practical.
- Use ESCO mappings as taxonomy support, not as unquestionable ground truth.
- Preserve the original extracted phrase when useful for debugging/provenance.
- Distinguish explicit skill mentions from inferred/semantic relationships.
- Measure extraction quality with labeled examples when changing extraction behavior.

Read [references/skill-extraction.md](references/skill-extraction.md) for taxonomy and evaluation rules.

## Evaluation

Use metrics that match the ML task.

For recommendation/ranking, consider:

- Precision@K;
- Recall@K;
- NDCG@K;
- MRR;
- coverage and useful failure analysis.

For skill extraction/classification, consider:

- precision;
- recall;
- F1;
- per-skill/category errors where meaningful.

For regression-style outputs, use metrics appropriate to the target rather than forcing ranking metrics onto them.

Always compare new behavior with a baseline. Keep duplicate or near-duplicate records from leaking across train/evaluation splits.

Read [references/evaluation-and-experiments.md](references/evaluation-and-experiments.md) when training, tuning, comparing, or promoting models.

## Reproducibility

Make experiments reproducible enough for another developer to rerun them.

Record, as applicable:

- code revision;
- dataset/snapshot identifier or query window;
- feature/preprocessing version;
- model/library version;
- parameters;
- random seed;
- evaluation metrics;
- artifact location/checksum.

Do not rely on an untracked notebook state as the only record of a result.

## Privacy and Fairness

Treat CV content as sensitive user data.

- Never commit real CVs, extracted CV text, or production user features.
- Never log full CV text or unnecessary personally identifying information.
- Do not use uploaded user CVs as training data unless the product explicitly defines an approved consent and data-governance path.
- Exclude names, photos, age, gender, nationality, religion, disability, and other protected/sensitive attributes from ranking features unless a legitimate product requirement explicitly requires handling them and the design has been reviewed.
- Do not infer protected attributes for ranking.
- Keep recommendations advisory; do not present similarity scores as objective measures of a person's worth or employability.

Use synthetic or sanitized fixtures in tests.

## Model Artifacts and Inference

Do not commit trained model binaries or large embedding artifacts to Git.

- Store production artifacts in the project's configured object storage when available.
- Store artifact metadata/version references separately from the binary.
- Pin the model identity/version used for production inference.
- Verify artifact compatibility before loading it.
- Load reusable inference models once per process or through an established cache; do not reload a large model for every request.
- Precompute job-side embeddings/features in batch when practical; compute/cached user-side representations after CV processing as appropriate.
- Avoid adding a dedicated vector database until measured scale or query requirements justify it.

Read [references/artifacts-and-inference.md](references/artifacts-and-inference.md) for promotion and serving rules.

## Cost and Dependency Rules

Keep core SkillSync functionality runnable without paid third-party model APIs.

Prefer:

- scikit-learn for classical baselines;
- sentence-transformers or another repo-approved local/open model stack for embeddings;
- CPU-friendly approaches first.

Do not add a GPU requirement, hosted LLM dependency, vector database, experiment platform, or heavy deep-learning framework unless the issue demonstrates a concrete need and the operational cost is acceptable.

Follow the repository dependency rules in `AGENTS.md`.

## Testing

Test ML code at multiple levels:

- unit-test normalization, preprocessing, and feature construction;
- test deterministic score/rank behavior with small fixtures;
- test inference input/output contracts;
- test handling of empty, malformed, and partial CV/job data;
- add regression tests for fixed bugs;
- run evaluation tests separately from fast unit tests when they require larger fixtures or model assets;
- do not require live external model/API calls in normal CI.

Read [references/testing-and-reproducibility.md](references/testing-and-reproducibility.md) when adding or changing ML tests.

## Definition of Done

Before finishing an ML task, verify that:

- the change stays within the issue scope;
- training, evaluation, and inference responsibilities remain separated;
- affected data/API contracts are explicit;
- preprocessing and feature behavior is tested;
- the new approach is compared against a baseline when model behavior changes;
- metrics and evaluation data are appropriate to the task;
- user CV data is not exposed in logs, tests, or Git;
- artifacts are versioned/stored according to project rules;
- runtime cost and latency are reasonable for the deployment target;
- relevant tests and evaluation checks pass;
- documentation is updated when a public ML contract or operational behavior changes.

# Model Artifacts and Inference

## Artifact Metadata

Track enough metadata to reproduce and safely load an artifact. Useful fields include:

```text
model_name
model_version
artifact_uri
artifact_checksum
created_at
code_revision
data_snapshot
preprocessing_version
metric_summary
```

Use the project's established metadata schema rather than creating duplicates.

## Storage

Do not commit large model binaries, embedding matrices, or user-derived feature dumps to Git.

Use configured object storage for production artifacts when available. Keep only small deterministic test fixtures in the repository.

## Loading

Validate expected model/preprocessing versions before inference.

Load heavyweight reusable models once per worker/process or through an established lazy singleton/cache. Avoid loading per HTTP request.

Fail clearly when an artifact is unavailable or incompatible. Do not silently fall back to an unrelated model version.

## Batch vs Online

Prefer batch computation for stable job-side features/embeddings. Use online computation only for user-specific or request-specific representations that cannot be prepared ahead of time.

Version stored embeddings/features. Recompute when their producing model or preprocessing contract changes.

## Serving Boundary

Expose a small inference interface to the backend, for example conceptually:

```python
rank_jobs(cv, jobs) -> ranked_matches
extract_skills(text) -> extracted_skills
```

Do not expose training internals to API routes.

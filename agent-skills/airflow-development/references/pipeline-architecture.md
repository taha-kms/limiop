# Pipeline Architecture

## Contents

- Ownership
- Preferred layout
- Pipeline stages
- Dependency direction
- Shared contracts
- Model workflows

## Ownership

The `airflow/` component owns scheduled and repeatable data orchestration. It does not own interactive application behavior.

Typical responsibilities:

- fetch external job data;
- preserve raw payloads;
- normalize source-specific records;
- deduplicate and enrich jobs;
- run data-quality checks;
- persist pipeline results;
- schedule expiration and analytics aggregation;
- orchestrate ML training/evaluation.

## Preferred Layout

Use the existing repository layout first. For new areas, prefer:

```text
airflow/
├── dags/
│   ├── job_ingestion.py
│   ├── job_enrichment.py
│   ├── job_expiration.py
│   └── model_training.py
├── src/
│   ├── ingestion/
│   │   ├── arbeitnow.py
│   │   ├── jobicy.py
│   │   ├── greenhouse.py
│   │   └── lever.py
│   ├── normalization/
│   ├── deduplication/
│   ├── enrichment/
│   ├── quality/
│   └── persistence/
└── tests/
```

Do not build every folder before it is needed.

## Pipeline Stages

Use explicit stages so data state is understandable:

```text
External API
    |
    v
Raw batch
    |
    v
Validation
    |
    v
Normalization
    |
    v
Deduplication
    |
    v
Enrichment
    |
    v
Quality gate
    |
    v
Application / analytics persistence
```

Not every source needs a separate Airflow task for every stage. The conceptual boundary matters more than multiplying task boxes.

## Dependency Direction

DAGs may import reusable pipeline modules. Reusable pipeline modules should not depend on DAG objects.

Prefer pure transformation functions where possible:

```python
def normalize_job(raw: RawJob) -> NormalizedJob:
    ...
```

This code should be testable without importing or starting Airflow.

Source clients should encapsulate source-specific HTTP behavior. Persistence modules should encapsulate database or object-storage writes. Transformations should not open database sessions as a side effect unless persistence is their explicit responsibility.

## Shared Contracts

Do not independently redefine the canonical application job shape in multiple components.

If the monorepo has a shared contract/package for canonical job fields, use it. If not, coordinate changes so backend persistence and Airflow normalization remain consistent.

Source-specific models may live in the Airflow/data layer because they represent ingestion contracts rather than application contracts.

## Model Workflows

Airflow orchestrates model work but does not own model implementation.

Prefer:

```text
model_training DAG
    -> select/version training data
    -> invoke ml/training code
    -> invoke ml/evaluation code
    -> persist artifact to object storage
    -> persist metadata/status
```

Keep model binaries out of Git and out of PostgreSQL large-object improvisations unless the architecture explicitly changes.

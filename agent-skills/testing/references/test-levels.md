# Test Levels

## Unit

Use for pure transformations, validation, normalization, scoring, parsing helpers, and isolated services with explicit dependencies.

Keep unit tests fast and deterministic.

## Integration

Use when correctness depends on a real subsystem boundary, especially:

- PostgreSQL semantics
- FastAPI request + service + persistence integration
- file/object-storage adapters when an emulator/test implementation exists
- Airflow DAG construction with installed providers

## End-to-end

Use sparingly for critical user journeys across the deployed or locally composed system.

Prefer a few high-value flows over hundreds of brittle browser scenarios.

## Evaluation

Use for ML quality, ranking quality, extraction quality, and data-quality metrics that are not ordinary pass/fail unit behavior.

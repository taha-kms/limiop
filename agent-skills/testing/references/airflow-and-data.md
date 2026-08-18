# Airflow and Data Tests

- Test DAG import/construction without triggering real external work.
- Keep transformation functions outside DAG definitions so they can be unit-tested normally.
- Use small provider-response fixtures representing valid, missing, malformed, and changed fields.
- Test normalization determinism.
- Test deduplication with strong identifiers and expected edge cases.
- Test reruns to prove idempotency.
- Test data-quality rejection/quarantine rules explicitly.
- Avoid live third-party API calls in normal CI.

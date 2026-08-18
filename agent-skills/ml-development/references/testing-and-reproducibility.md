# Testing and Reproducibility

## Fast Unit Tests

Use small synthetic/sanitized fixtures to test:

- preprocessing;
- text normalization;
- feature construction;
- score combination;
- ranking order;
- empty inputs;
- malformed inputs;
- serialization/deserialization contracts.

Keep normal CI tests deterministic and network-free.

## Model-Dependent Tests

When a test requires a model artifact, prefer a tiny deterministic fixture/model or a separately marked integration/evaluation test. Do not force normal CI to download large public models on every run unless the repository intentionally caches/pins them.

## Regression Tests

For fixed ML bugs, add the smallest fixture that reproduces the failure and assert the expected behavior.

## Reproducibility

Set random seeds when randomness affects results and record them with experiment metadata.

Pin production model identity and relevant preprocessing versions. Avoid relying on "latest" model aliases.

## Evaluation Tests

Keep metric/evaluation tests distinct from unit tests when they require larger datasets or longer runtime. Make thresholds explicit and avoid brittle checks on insignificant floating-point differences.

## Privacy

Never use real user CVs as committed test fixtures. Remove names, contact details, addresses, and other identifying information from any externally sourced example that is retained for testing.

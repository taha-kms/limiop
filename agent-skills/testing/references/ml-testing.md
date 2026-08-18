# ML Testing

Separate correctness tests from evaluation.

Correctness tests should cover:

- deterministic preprocessing
- token/skill normalization
- vector dimensions and types
- scorer bounds/order
- empty/invalid input handling
- artifact/version compatibility

Evaluation should use fixed versioned datasets or manifests and report the metrics selected by the ML development workflow.

Use tolerances for floating-point comparisons where exact equality is not meaningful.

Do not commit private CVs or large generated model artifacts as test fixtures.

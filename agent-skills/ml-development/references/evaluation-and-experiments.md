# Evaluation and Experiments

## Experiment Record

For meaningful model comparisons, record:

- experiment purpose;
- code revision;
- dataset/snapshot identifier;
- split strategy;
- preprocessing/feature version;
- model and parameters;
- random seed;
- metrics;
- important error-analysis notes;
- artifact identifier when promoted.

A markdown/JSON record in the repository is acceptable initially if it follows existing conventions. Do not add an experiment-tracking platform merely to obtain screenshots for a portfolio.

## Splitting

Choose splits that match the intended claim.

- Use time-based splits for future-facing job-market/recommendation claims when feasible.
- Group duplicates/near-duplicates before splitting.
- Keep company/template duplication in mind when evaluating generalization.
- Do not tune repeatedly on the final test set.

## Baseline Comparison

For any model behavior change, compare the candidate against the currently accepted baseline using the same evaluation set and metric definitions.

Do not promote complexity when improvements are negligible, unstable, or achieved by leakage.

## Error Analysis

Inspect representative failures, not just aggregate metrics.

Track categories such as:

- missing skill aliases;
- overly generic semantic matches;
- title mismatch;
- location/filter errors;
- sparse CVs;
- unusually long job descriptions;
- multilingual content.

## Promotion

Promote a candidate only when:

- required metrics meet the task threshold or improve meaningfully;
- regression checks pass;
- runtime cost is acceptable;
- artifact metadata is complete;
- inference code supports the artifact version.

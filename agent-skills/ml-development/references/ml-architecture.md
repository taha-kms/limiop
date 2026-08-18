# ML Architecture

## Ownership

Keep ML code focused on learned/statistical behavior and the transformations required specifically for that behavior.

```text
Data engineering                     ML                              Backend
----------------                     --                              -------
canonical jobs      ------------->   features/preprocessing   --->  inference interface
normalized skills  ------------->   training/evaluation       --->  response/service logic
historical data    ------------->   batch representations
```

Airflow may schedule training, evaluation, embedding refreshes, or batch scoring, but DAG files must call reusable ML functions rather than contain training logic.

## Suggested Structure

```text
ml/
├── preprocessing/
│   ├── cv_text.py
│   ├── job_text.py
│   └── skill_features.py
├── features/
│   ├── lexical.py
│   └── semantic.py
├── training/
│   └── train_matcher.py
├── evaluation/
│   ├── metrics.py
│   └── evaluate_matcher.py
├── inference/
│   ├── matcher.py
│   └── skill_extractor.py
├── experiments/
└── tests/
```

Adapt names to the existing repository rather than creating parallel structures.

## Stable Interfaces

Prefer explicit typed inputs/outputs at component boundaries. Avoid passing arbitrary dictionaries deep through ML code when a stable model/schema already exists.

Keep production inference deterministic for identical inputs/model versions except where randomness is explicitly required.

## Avoid Circular Ownership

Do not let:

- ML code perform HTTP request routing;
- ML code own authentication/authorization;
- backend routes implement training pipelines;
- Airflow DAGs own feature algorithms;
- frontend code calculate authoritative match scores;
- training code write application records through ad-hoc SQL when a repository persistence contract exists.

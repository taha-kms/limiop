# Skill Extraction and ESCO

## Extraction Contract

Represent extracted skills with enough provenance to distinguish what the source said from how SkillSync normalized it.

Useful fields may include:

```text
source_text
normalized_skill_name
canonical_skill_id
confidence
extraction_method
```

Use the repository's actual schema if it differs.

## Explicit vs Inferred Skills

Do not silently present inferred skills as if they were explicitly written in a CV or job description.

Preserve a distinction between:

- explicit mention;
- normalized alias;
- broader/narrower taxonomy relationship;
- inferred semantic relationship.

## ESCO

Use ESCO to support canonical skill/occupation mappings and multilingual aliases where useful.

Do not force every phrase into an ESCO concept when confidence is poor. Preserve unresolved skills rather than manufacturing a mapping.

## Evaluation

Use labeled examples representative of SkillSync jobs/CVs. Measure precision, recall, and F1 for extraction changes.

Include difficult cases such as:

- aliases (`Postgres` vs `PostgreSQL`);
- ambiguous short forms;
- multi-word technologies;
- tools mentioned in project descriptions but not claimed as skills;
- negated requirements;
- malformed job HTML/text;
- multilingual terms when supported.

# Gold-label resolution through alias table v2

This measurement asks a narrower, reproducible question than the Phase B
span-overlap evaluation: for each committed gold mention, does at least one of
its recorded annotator labels resolve exactly through the shipped alias-table
resolver?

## Result

| vocabulary version | resolved gold mentions | total gold mentions | gold-label resolution rate |
| --- | ---: | ---: | ---: |
| `2026.08.25.1` | 455 | 2,059 | **0.220981 (22.1%)** |
| `2026.08.28.1` | 455 | 2,059 | **0.220981 (22.1%)** |

`2026.08.28.1` removes 50 of the 182 surface forms and resolves exactly the
same gold labels, which is how the
[collision audit](alias-collision-audit.md) established that those forms were
not carrying the vocabulary. This measurement is the one that could judge that
change: it covers all 78 gold postings rather than the 14 still fetchable, and
it credits nothing for partial overlap.

**This 0.220981 gold-label resolution rate is not comparable to the 0.412
span-overlap recall.** This rate resolves committed annotator labels as exact
candidate terms. The 0.412 result matched curated forms inside posting
description text and counted matches that overlapped gold offsets. That frozen
description text was not committed, so the original span-overlap score cannot
be rerun from the repository.

The low rate is the finding. Gold labels are annotator descriptions, while the
curated aliases are corpus-frequency terms. No substring, prefix, stem, or
fuzzy matching is added to make the number larger.

## Reproduce

From the repository root:

```console
cd backend
./.venv/bin/python scripts/measure_gold_label_resolution.py
```

The script reads only
`docs/skill-model-measurement/gold-set.json` and the packaged
`backend/app/modules/skills/data/aliases.v2.json`. It requires no network or
database. Its output is:

```json
{
  "metric": "gold-label resolution rate",
  "vocabulary_version": "2026.08.25.1",
  "gold_mentions": 2059,
  "resolved_mentions": 455,
  "rate": 0.220981
}
```

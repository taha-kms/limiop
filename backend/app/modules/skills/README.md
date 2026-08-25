# Canonical skills

Known skills are identified by UUID, not by their preferred label. Labels may
change without changing the concept that job and candidate records will refer
to. An ESCO URI is optional interoperability metadata on a concept; a null URI
is ordinary and does not make the concept less canonical.

`data/aliases.v1.json` remains the readable demonstration vocabulary with 9
concepts and 21 surface forms. `data/aliases.v2.json` publishes the measured
curated arm as 56 concepts and 182 normalized-distinct surface forms. The
version registry keeps both artifacts loadable and selects v2 as the default.
Each artifact carries its own vocabulary version, publishes surface forms
separately from concepts, and can map one form to more than one concept when
the wording is ambiguous. A vocabulary change creates a new artifact rather
than silently changing a previous version.

The curated arm contains 184 raw forms. `problem solving` and
`problem-solving` normalize to the same lookup form, as do `detail-oriented`
and `detail oriented`. V2 keeps the first measured spelling in each pair, so
the published artifact contains 182 lookup forms without changing the
normalizer or inventing aliases.

The known-skill resolver has three outcomes:

- `resolved`: exactly one published concept matches;
- `ambiguous`: the published form names more than one concept, and all are
  returned in stable order;
- `unmapped`: the form is absent, and no concept is guessed or created.

`unmapped` is the seam for the unknown-skill gate tracked separately. This
module does not decide whether an unknown term is legitimate enough to store.

Resolution is exact after Unicode compatibility normalization, case folding,
folding whitespace/hyphens/underscores, and trimming surrounding prose
punctuation. Symbols with meaning in technical names, including `#` and `+`,
are preserved. Broader stemming or substring matching is intentionally absent
because it would reintroduce false positives such as `own`, `projects`, and
`testing` from the measured research vocabulary.

`TEXT_MATCHING_HAZARD_FORMS` is importable from `app.modules.skills` for text
extractors to handle explicitly. It names the nine published forms of three
characters or fewer: `ai`, `aws`, `b2b`, `gcp`, `gpu`, `ml`, `own`, `qa`, and
`ux`. Exact candidate-term resolution does not scan prose, so these forms are
safe at this boundary. They are hazardous for text extraction: the
[frozen partial scores](../../../../docs/skill-model-measurement/in-progress/partial-scores.md)
record 57 ordinary-verb matches for `own` and 330 matches for `ai`.

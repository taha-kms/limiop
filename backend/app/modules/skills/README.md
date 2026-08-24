# Canonical skills

Known skills are identified by UUID, not by their preferred label. Labels may
change without changing the concept that job and candidate records will refer
to. An ESCO URI is optional interoperability metadata on a concept; a null URI
is ordinary and does not make the concept less canonical.

`data/aliases.v1.json` is the reviewable alias-table artifact. It carries its
own vocabulary version, publishes surface forms separately from concepts, and
can map one form to more than one concept when the wording is ambiguous. A
vocabulary change creates a new versioned artifact rather than silently
changing the meaning of a previous version.

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

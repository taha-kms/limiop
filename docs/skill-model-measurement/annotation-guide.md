# Annotation guide

Both annotators work from this document and nothing else. In particular,
neither sees any candidate vocabulary — not the curated list, not ESCO, not the
free-text terms — because a gold set produced with a vocabulary in view measures
that vocabulary rather than the postings.

Frozen before the first posting was read. The measurement design that requires
it is `../superpowers/specs/2026-08-23-skill-model-measurement-design.md`.

## What you are doing

Reading a job posting and recording every skill it mentions.

You are not judging whether a skill is important, whether the posting is well
written, or whether a candidate would need it. You are recording what the
posting says.

## What counts as a mention

A **mention** is a contiguous span of the description that asserts a skill in
connection with doing this job.

Record a mention when the posting associates the skill with the role, whether
it frames it as a hard requirement, a preference, or simply as context:

- `You will need strong SQL` — yes.
- `Our stack is Python and Go` — yes. Framed as context, still the skills of
  the job.
- `You will have the chance to learn Rust` — yes, as `preferred`. The job
  develops it.
- `We use Workday for expense reports` — no. A tool the company happens to own,
  not a skill of this role.
- `No prior Kubernetes experience is required` — no. The posting is denying it.

Repeated skills are recorded once per posting. If `Python` appears four times,
record the first span. Recall is measured over posting-and-skill pairs, so a
second occurrence adds nothing.

## What does not count

- Years of experience. `5+ years` is a quantity, not a skill.
- Degrees and qualifications. `BSc in Computer Science` is not a skill.
  A named professional certification is — see `language and certification`
  below.
- Salary, benefits, and working arrangements.
- Seniority titles. `Senior`, `Staff`, `Lead` describe the role, not a skill.
- The employer's own products, unless working with them is the job.

## Categories

Every mention is typed. The types are ESCO's four sub-pillars, given here as
operational tests rather than definitions, because the tests are what two people
can apply consistently.

| Category | Test | Examples |
| --- | --- | --- |
| `knowledge` | A thing you know about. A technology, tool, domain, standard, or method. Usually a noun. | `Python`, `Kubernetes`, `GDPR`, `double-entry bookkeeping`, `food safety` |
| `skill` | An action you can perform. Usually a verb phrase. | `debug distributed systems`, `write technical documentation`, `run user research` |
| `transversal` | A general working capability, not specific to any domain. | `teamwork`, `attention to detail`, `stakeholder communication` |
| `language` | A natural language, with its level if stated. | `German (C1)`, `fluent English` |

When a mention could be `knowledge` or `skill`, prefer `knowledge` if a noun
names a thing. The categories exist so the production scope can be narrowed
later by filtering; they are not a philosophical claim, and getting the boundary
between the first two exactly right matters less than being consistent.

**A category disagreement is not a different mention.** If both annotators
record `Kubernetes` and disagree on its category, they agree the posting
mentions Kubernetes. Label agreement and category agreement are measured
separately.

## The requirement flag

| Value | When |
| --- | --- |
| `required` | The posting states it as necessary — `must`, `required`, `you have` |
| `preferred` | Framed as a bonus — `nice to have`, `a plus`, `ideally` |
| `unclear` | Mentioned without framing, including stack-description context |

A nice-to-have and a hard requirement are different signals to any matcher, and
they cannot be separated after the fact, so they are separated now.

## Writing a label

The label is **your name for the concept**, not the words the posting used.

Two rules, both checked mechanically:

1. **At most four words and 64 characters.** Anything longer is a copied clause
   rather than a name.
2. **A canonical name, not a quotation.** If the posting says `must be
   comfortable owning services end to end`, the label is `service ownership`.

This is not only a style rule. Provider prose is untrusted and is never
republished, so the committed artifact holds your labels and the character
offsets of the span — never the span's text. If you cannot name something in
four words, that is good evidence it is a job duty rather than a skill, and it
probably should not be a mention.

Reuse your own labels across postings. `Postgres` in one posting and
`PostgreSQL` in the next should be one label, chosen once and kept. You are
building a naming scheme as you go; that is expected, and it is the thing the
exercise is trying to observe.

## Language

Record the language you observe the posting to be written in, as `en`, `de`, or
`other`. This is compared against the automatic detector, which is how the
detector's error rate gets measured.

If a posting is genuinely bilingual, record the language of the majority of the
body text.

## Output format

One JSON object per posting.

```json
{
  "posting": "greenhouse:hudl:4123456",
  "description_sha256": "9f2b...",
  "observed_language": "en",
  "mentions": [
    {
      "label": "Kubernetes",
      "category": "knowledge",
      "requirement": "required",
      "start": 412,
      "end": 422
    }
  ]
}
```

`start` and `end` are character offsets into the stored description. `posting`
is the provenance key. A posting with no skill mentions gets an empty `mentions`
list, which is a finding rather than a gap.

## If the guide is unclear

Note it and make the call. Do not ask the other annotator, and do not change the
guide mid-pass — a guide that shifts underneath two annotators makes their
agreement figure meaningless.

If set-level agreement comes out low, the guide is the suspect, and it gets
revised and both passes re-run rather than the disagreements being quietly
adjudicated away.
